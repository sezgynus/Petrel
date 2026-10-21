// SPDX-License-Identifier: GPL-3.0-or-later
/* Standard TTY frontend; a single privileged broker owns the hardware transport.
 * Backend records: u8 op, le32 TX epoch, le16 length, payload (<=248 bytes).
 * Kernel -> broker: 1 TX, 2 BAUD (le32).
 * Broker -> kernel: 1 RX, 3 TX-complete (le32 byte count), 4 READY (u8).
 * Epochs stop a late completion after tcflush from consuming a newer TX count.
 */
#include <linux/device.h>
#include <linux/fs.h>
#include <linux/kfifo.h>
#include <linux/miscdevice.h>
#include <linux/module.h>
#include <linux/mutex.h>
#include <linux/poll.h>
#include <linux/serial.h>
#include <linux/spinlock.h>
#include <linux/tty.h>
#include <linux/tty_driver.h>
#include <linux/tty_flip.h>
#include <linux/uaccess.h>
#include <linux/version.h>
#if LINUX_VERSION_CODE >= KERNEL_VERSION(6, 12, 0)
#include <linux/unaligned.h>
#else
#include <asm/unaligned.h>
#endif

#define CAPACITY 65536
#define PAYLOAD 248
#define HEADER 7
#define CLOCK 15667200U
static struct tty_driver *driver;
static struct tty_port port;
static struct device *parent;
static DEFINE_KFIFO(queue, unsigned char, CAPACITY);
static DEFINE_SPINLOCK(state_lock);
static DEFINE_MUTEX(read_lock);
static DEFINE_MUTEX(rx_lock);
static DECLARE_WAIT_QUEUE_HEAD(backend_wait);
static bool attached, ready;
static unsigned int pending, baud = 115200, epoch = 1;

/* Caller holds state_lock. Queue always contains complete records. */
static bool enqueue(u8 op, const u8 *data, unsigned int size)
{
	u8 header[HEADER];
	if (kfifo_avail(&queue) < HEADER + size)
		return false;
	header[0] = op;
	put_unaligned_le32(epoch, header + 1);
	put_unaligned_le16(size, header + 5);
	kfifo_in(&queue, header, HEADER);
	kfifo_in(&queue, data, size);
	wake_up_interruptible(&backend_wait);
	return true;
}

static bool enqueue_baud(void)
{
	u8 data[4];
	put_unaligned_le32(baud, data);
	return enqueue(2, data, sizeof(data));
}

static unsigned int actual_baud(unsigned int requested)
{
	unsigned int divisor;
	if (requested < 15300 || requested > CLOCK)
		return 0;
	divisor = DIV_ROUND_CLOSEST(CLOCK, requested);
	if (!divisor || divisor > 1023)
		return 0;
	return DIV_ROUND_CLOSEST(CLOCK, divisor);
}

static int activate(struct tty_port *p, struct tty_struct *tty)
{
	unsigned long flags;
	int ret = 0;
	spin_lock_irqsave(&state_lock, flags);
	if (!ready)
		ret = -EIO;
	else {
		baud = actual_baud(tty_get_baud_rate(tty));
		if (!baud)
			baud = 115200;
		if (!enqueue_baud())
			ret = -EAGAIN;
	}
	spin_unlock_irqrestore(&state_lock, flags);
	return ret;
}

static const struct tty_port_operations port_ops = { .activate = activate };

static int uart_open(struct tty_struct *tty, struct file *file)
{
	return tty_port_open(&port, tty, file);
}

static void uart_close(struct tty_struct *tty, struct file *file)
{
	tty_port_close(&port, tty, file);
}

static void uart_hangup(struct tty_struct *tty)
{
	tty_port_hangup(&port);
}

#if LINUX_VERSION_CODE >= KERNEL_VERSION(6, 6, 0)
static ssize_t uart_write(struct tty_struct *tty, const u8 *data, size_t size)
#else
static int uart_write(struct tty_struct *tty, const unsigned char *data, int size)
#endif
{
	unsigned long flags;
	unsigned int count = min_t(unsigned int, size, PAYLOAD);
	int ret;
	spin_lock_irqsave(&state_lock, flags);
	if (!ready)
		ret = -EIO;
	else if (pending + count > CAPACITY || !enqueue(1, data, count))
		ret = 0;
	else {
		pending += count;
		ret = count;
	}
	spin_unlock_irqrestore(&state_lock, flags);
	return ret;
}

static unsigned int write_room(struct tty_struct *tty)
{
	unsigned long flags;
	unsigned int room;
	spin_lock_irqsave(&state_lock, flags);
	room = ready && kfifo_avail(&queue) >= HEADER + PAYLOAD
		? min_t(unsigned int, PAYLOAD, CAPACITY - pending) : 0;
	spin_unlock_irqrestore(&state_lock, flags);
	return room;
}

static unsigned int chars_in_buffer(struct tty_struct *tty)
{
	return READ_ONCE(pending);
}

static void flush_buffer(struct tty_struct *tty)
{
	unsigned long flags;
	spin_lock_irqsave(&state_lock, flags);
	epoch++;
	pending = 0;
	kfifo_reset(&queue);
	if (attached)
		enqueue_baud();
	spin_unlock_irqrestore(&state_lock, flags);
	tty_port_tty_wakeup(&port);
}

static void set_termios(struct tty_struct *tty, const struct ktermios *old)
{
	unsigned int requested = tty_get_baud_rate(tty), actual;
	unsigned long flags;
	actual = actual_baud(requested);
	spin_lock_irqsave(&state_lock, flags);
	/* Only 8N1. Report unsupported settings honestly through termios readback. */
	if (!actual || (tty->termios.c_cflag & (CSIZE | PARENB | CSTOPB | CRTSCTS)) != CS8) {
		tty_termios_copy_hw(&tty->termios, old);
	} else {
		unsigned int previous = baud;
		baud = actual;
		if (attached && !enqueue_baud()) {
			baud = previous;
			tty_termios_copy_hw(&tty->termios, old);
		} else {
			tty_termios_encode_baud_rate(&tty->termios, actual, actual);
		}
	}
	tty->termios.c_cflag |= CLOCAL | CREAD;
	spin_unlock_irqrestore(&state_lock, flags);
}

static const struct tty_operations tty_ops = {
	.open = uart_open, .close = uart_close, .hangup = uart_hangup,
	.write = uart_write, .write_room = write_room,
	.chars_in_buffer = chars_in_buffer, .flush_buffer = flush_buffer,
	.set_termios = set_termios,
};

static int backend_open(struct inode *inode, struct file *file)
{
	unsigned long flags;
	int ret = 0;
	spin_lock_irqsave(&state_lock, flags);
	if (attached)
		ret = -EBUSY;
	else {
		attached = true;
		ready = false;
		epoch++;
		pending = 0;
		kfifo_reset(&queue);
		enqueue_baud();
	}
	spin_unlock_irqrestore(&state_lock, flags);
	return ret;
}

static int backend_release(struct inode *inode, struct file *file)
{
	unsigned long flags;
	spin_lock_irqsave(&state_lock, flags);
	attached = ready = false;
	epoch++;
	pending = 0;
	kfifo_reset(&queue);
	spin_unlock_irqrestore(&state_lock, flags);
	tty_port_tty_hangup(&port, false);
	wake_up_interruptible(&backend_wait);
	return 0;
}

static ssize_t backend_read(struct file *file, char __user *buffer,
			    size_t size, loff_t *offset)
{
	u8 record[HEADER + PAYLOAD];
	unsigned long flags;
	unsigned int count;
	int ret;
	if (size < sizeof(record))
		return -EMSGSIZE;
	if (mutex_lock_interruptible(&read_lock))
		return -ERESTARTSYS;
	again:
	spin_lock_irqsave(&state_lock, flags);
	if (kfifo_len(&queue) < HEADER) {
		spin_unlock_irqrestore(&state_lock, flags);
		if (file->f_flags & O_NONBLOCK) {
			ret = -EAGAIN;
			goto out;
		}
		ret = wait_event_interruptible(backend_wait, !kfifo_is_empty(&queue));
		if (ret)
			goto out;
		goto again;
	}
	count = kfifo_out_peek(&queue, record, HEADER);
	count = HEADER + get_unaligned_le16(record + 5);
	/* Copy to a local record atomically; a concurrent flush invalidates its epoch. */
	count = kfifo_out(&queue, record, count);
	spin_unlock_irqrestore(&state_lock, flags);
	ret = copy_to_user(buffer, record, count) ? -EFAULT : count;
	if (ret < 0) /* Cannot replay a possibly delivered TX: signal broken transport. */
		tty_port_tty_hangup(&port, false);
	out:
	mutex_unlock(&read_lock);
	return ret;
}

static ssize_t backend_write(struct file *file, const char __user *buffer,
			     size_t size, loff_t *offset)
{
	u8 record[HEADER + PAYLOAD];
	unsigned int length, accepted;
	unsigned long flags;
	bool hangup = false;
	ssize_t ret = size;
	if (size < HEADER || size > sizeof(record))
		return -EINVAL;
	if (copy_from_user(record, buffer, size))
		return -EFAULT;
	length = get_unaligned_le16(record + 5);
	if (size != HEADER + length)
		return -EINVAL;
	if (record[0] == 1) {
		if (mutex_lock_interruptible(&rx_lock))
			return -ERESTARTSYS;
		if (!READ_ONCE(ready))
			ret = -EIO;
		else {
			accepted = tty_insert_flip_string(&port, record + HEADER, length);
			if (accepted) {
				tty_flip_buffer_push(&port);
				ret = HEADER + accepted;
			} else
				ret = -EAGAIN;
		}
		mutex_unlock(&rx_lock);
		return ret;
	}
	spin_lock_irqsave(&state_lock, flags);
	if (record[0] == 3 && length == 4) {
		if (get_unaligned_le32(record + 1) == epoch)
			pending -= min(pending, get_unaligned_le32(record + HEADER));
	} else if (record[0] == 4 && length == 1) {
		ready = record[HEADER] != 0;
		if (!ready) {
			epoch++;
			pending = 0;
			kfifo_reset(&queue);
			hangup = true;
		}
	} else
		ret = -EINVAL;
	spin_unlock_irqrestore(&state_lock, flags);
	if (hangup)
		tty_port_tty_hangup(&port, false);
	tty_port_tty_wakeup(&port);
	return ret;
}

static __poll_t backend_poll(struct file *file, poll_table *wait)
{
	__poll_t result = EPOLLOUT | EPOLLWRNORM;
	poll_wait(file, &backend_wait, wait);
	if (!kfifo_is_empty(&queue))
		result |= EPOLLIN | EPOLLRDNORM;
	return result;
}

static const struct file_operations backend_ops = {
	.owner = THIS_MODULE, .open = backend_open, .release = backend_release,
	.read = backend_read, .write = backend_write, .poll = backend_poll,
	.llseek = no_llseek,
};
static struct miscdevice backend = {
	.minor = MISC_DYNAMIC_MINOR, .name = "dwin-uart-backend",
	.fops = &backend_ops, .mode = 0600,
};

static int __init dwin_init(void)
{
	struct device *device;
	int ret;
	driver = tty_alloc_driver(1, TTY_DRIVER_REAL_RAW | TTY_DRIVER_DYNAMIC_DEV |
				 TTY_DRIVER_RESET_TERMIOS);
	if (IS_ERR(driver))
		return PTR_ERR(driver);
	tty_port_init(&port);
	port.ops = &port_ops;
	driver->driver_name = "dwin_uart";
	driver->name = "ttyDWIN";
	driver->type = TTY_DRIVER_TYPE_SERIAL;
	driver->subtype = SERIAL_TYPE_NORMAL;
	driver->init_termios = tty_std_termios;
	driver->init_termios.c_iflag = 0;
	driver->init_termios.c_oflag = 0;
	driver->init_termios.c_lflag = 0;
	driver->init_termios.c_cflag = B115200 | CS8 | CREAD | CLOCAL;
	tty_termios_encode_baud_rate(&driver->init_termios, 115200, 115200);
	tty_set_operations(driver, &tty_ops);
	ret = tty_register_driver(driver);
	if (ret)
		goto free_driver;
	parent = root_device_register("dwin-uart");
	if (IS_ERR(parent)) {
		ret = PTR_ERR(parent);
		goto unregister;
	}
	device = tty_port_register_device(&port, driver, 0, parent);
	if (IS_ERR(device)) {
		ret = PTR_ERR(device);
		goto free_parent;
	}
	ret = misc_register(&backend);
	if (!ret)
		return 0;
	tty_unregister_device(driver, 0);
	free_parent:
	root_device_unregister(parent);
	unregister:
	tty_unregister_driver(driver);
	free_driver:
	tty_driver_kref_put(driver);
	tty_port_destroy(&port);
	return ret;
}

static void __exit dwin_exit(void)
{
	misc_deregister(&backend);
	tty_unregister_device(driver, 0);
	root_device_unregister(parent);
	tty_unregister_driver(driver);
	tty_driver_kref_put(driver);
	tty_port_destroy(&port);
}
module_init(dwin_init);
module_exit(dwin_exit);
MODULE_DESCRIPTION("DWIN auxiliary UART TTY with broker transport");
MODULE_AUTHOR("Petrel contributors");
MODULE_LICENSE("GPL");
