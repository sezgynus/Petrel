// SPDX-License-Identifier: GPL-3.0-or-later
/* Single-threaded Linux DWIN transport. No UI or Python runtime dependency. */
#define _GNU_SOURCE
#include <errno.h>
#include <fcntl.h>
#include <getopt.h>
#include <math.h>
#include <poll.h>
#include <signal.h>
#include <stdbool.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/file.h>
#include <sys/ioctl.h>
#include <sys/socket.h>
#include <sys/stat.h>
#include <sys/un.h>
#include <termios.h>
#include <time.h>
#include <unistd.h>

#define LIMIT 65536U
#define PAYLOAD 248U
#define RECORD 7U
#define CLOCK_HZ 15667200U
static const uint8_t tail[] = {0xcc, 0x33, 0xc3, 0x3c};
enum kind { DISPLAY, PROBE, BAUD, AUX, DRAIN };
struct frame {
    struct frame *next;
    size_t size, offset;
    enum kind kind;
    bool last;
    uint8_t data[];
};
struct queue { struct frame *head, *last; size_t bytes; };
struct broker {
    const char *port_path, *socket_path, *backend_path;
    int listener, uart, client, backend;
    bool online, tty_ready, configuring, needs_config, tx_busy;
    unsigned turn, baud, tx_epoch, tx_count;
    double probe_at, probe_deadline, uart_retry, backend_retry, aux_ready, tx_deadline, rx_retry;
    struct queue display_tx, display_rx, aux_tx;
    struct frame *active;
    uint8_t rx[4096], aux_rx[LIMIT];
    size_t rx_size, aux_head, aux_size;
};
static volatile sig_atomic_t stopping;

static void stop_signal(int sig) { (void)sig; stopping = 1; }
static double now(void)
{
    struct timespec ts;
    if (clock_gettime(CLOCK_MONOTONIC, &ts) < 0) abort();
    return (double)ts.tv_sec + (double)ts.tv_nsec / 1e9;
}
static unsigned le16(const uint8_t *p) { return p[0] | (unsigned)p[1] << 8; }
static uint32_t le32(const uint8_t *p)
{
    return p[0] | (uint32_t)p[1] << 8 | (uint32_t)p[2] << 16 | (uint32_t)p[3] << 24;
}
static void put32(uint8_t *p, uint32_t n)
{
    for (unsigned i = 0; i < 4; ++i) p[i] = (uint8_t)(n >> (8 * i));
}
static bool again(void) { return errno == EAGAIN || errno == EWOULDBLOCK || errno == EINTR; }
static void report(const char *where)
{
    fprintf(stderr, "petrel-dwin: %s: %s\n", where, strerror(errno));
}
static bool append(struct queue *q, const uint8_t *data, size_t size, enum kind kind, bool last)
{
    if (!size || size > LIMIT - q->bytes) { errno = ENOBUFS; return false; }
    struct frame *f = malloc(sizeof(*f) + size);
    if (!f) return false;
    *f = (struct frame){.size = size, .kind = kind, .last = last};
    memcpy(f->data, data, size);
    if (q->last) q->last->next = f; else q->head = f;
    q->last = f;
    q->bytes += size;
    return true;
}
static struct frame *pop(struct queue *q)
{
    struct frame *f = q->head;
    if (f) {
        q->head = f->next;
        if (!q->head) q->last = NULL;
        q->bytes -= f->size;
        f->next = NULL;
    }
    return f;
}
static void clear(struct queue *q)
{
    struct frame *f;
    while ((f = pop(q))) free(f);
}
static void close_fd(int *fd) { if (*fd >= 0) close(*fd); *fd = -1; }
static void drop_client(struct broker *b)
{
    close_fd(&b->client);
    clear(&b->display_tx);
    clear(&b->display_rx);
    /* An active partial display command must still finish without interleaving.
     * An unsent drain barrier must not leak an ACK to a subsequent client. */
    if (b->active && b->active->kind == DRAIN) {
        free(b->active);
        b->active = NULL;
    }
}
static void disconnect_transport(struct broker *b, const char *reason)
{
    if (reason) report(reason);
    drop_client(b);
    close_fd(&b->uart);
    close_fd(&b->backend); /* Kernel hangs up every open ttyDWIN client. */
    free(b->active);
    b->active = NULL;
    clear(&b->aux_tx);
    b->online = b->tty_ready = b->configuring = b->tx_busy = false;
    b->needs_config = true;
    b->rx_size = b->aux_head = b->aux_size = 0;
    b->probe_deadline = b->aux_ready = b->rx_retry = 0;
    b->uart_retry = b->backend_retry = now() + 1;
}
static bool control(struct broker *b, unsigned op, uint32_t epoch, const uint8_t *data, size_t size)
{
    uint8_t record[RECORD + PAYLOAD];
    record[0] = (uint8_t)op;
    put32(record + 1, epoch);
    record[5] = (uint8_t)size;
    record[6] = (uint8_t)(size >> 8);
    memcpy(record + RECORD, data, size);
    ssize_t n = write(b->backend, record, RECORD + size);
    if (n != (ssize_t)(RECORD + size)) { if (n >= 0) errno = EIO; return false; }
    return true;
}
static bool configure_aux(struct broker *b, unsigned requested)
{
    if (requested < 15300 || requested > CLOCK_HZ) { errno = EINVAL; return false; }
    /* Match Python round() for exact halfway cases in the panel divisor. */
    unsigned div = CLOCK_HZ / requested, rem = CLOCK_HZ % requested;
    if ((uint64_t)rem * 2 > requested || ((uint64_t)rem * 2 == requested && (div & 1))) ++div;
    if (!div || div > 1023) { errno = EINVAL; return false; }
    uint8_t frame[] = {0xaa, 0x38, (uint8_t)(div >> 8), (uint8_t)div, 0xcc, 0x33, 0xc3, 0x3c};
    if (!append(&b->aux_tx, frame, sizeof(frame), BAUD, false)) return false;
    b->baud = (CLOCK_HZ + div / 2) / div;
    b->configuring = true;
    b->needs_config = false;
    return true;
}
static bool queue_aux(struct broker *b, const uint8_t *data, size_t size)
{
    size_t offset = 0;
    while (offset < size) {
        size_t count = size - offset;
        if (count > PAYLOAD) count = PAYLOAD;
        for (size_t i = 0; i + sizeof(tail) <= count; ++i) {
            if (!memcmp(data + offset + i, tail, sizeof(tail))) { count = i + 3; break; }
        }
        uint8_t frame[PAYLOAD + 6];
        frame[0] = 0xaa; frame[1] = 0x39;
        memcpy(frame + 2, data + offset, count);
        memcpy(frame + 2 + count, tail, sizeof(tail));
        offset += count;
        if (!append(&b->aux_tx, frame, count + 6, AUX, offset == size)) return false;
    }
    return true;
}
static int open_backend(const char *path)
{
#ifdef DWIN_TEST_BACKEND
    /* CI's packet backend replaces only the misc fd. Production has no socket
     * backend or test-only command-line switch. Kernel CI uses the real fd. */
    struct stat info;
    if (stat(path, &info) == 0 && S_ISSOCK(info.st_mode)) {
        struct sockaddr_un address = {.sun_family = AF_UNIX};
        if (strlen(path) >= sizeof(address.sun_path)) { errno = ENAMETOOLONG; return -1; }
        strcpy(address.sun_path, path);
        int fd = socket(AF_UNIX, SOCK_SEQPACKET | SOCK_CLOEXEC, 0);
        if (fd < 0) return -1;
        if (connect(fd, (struct sockaddr *)&address, sizeof(address)) < 0 ||
            fcntl(fd, F_SETFL, O_NONBLOCK) < 0) { close(fd); return -1; }
        return fd;
    }
#endif
    return open(path, O_RDWR | O_NONBLOCK | O_CLOEXEC);
}
static bool backend_tick(struct broker *b)
{
    double current = now();
    if (b->backend < 0) {
        if (current < b->backend_retry) return true;
        b->backend = open_backend(b->backend_path);
        if (b->backend < 0) { b->backend_retry = current + 1; return true; }
        b->needs_config = true;
    }
    if (b->tx_busy) {
        if (current < b->tx_deadline) return true;
        uint8_t count[4]; put32(count, b->tx_count);
        if (!control(b, 3, b->tx_epoch, count, sizeof(count))) return false;
        b->tx_busy = false;
    }
    if (b->aux_size && b->tty_ready && current >= b->rx_retry) {
        uint8_t record[RECORD + PAYLOAD] = {1};
        size_t size = b->aux_size < PAYLOAD ? b->aux_size : PAYLOAD;
        record[5] = (uint8_t)size;
        for (size_t i = 0; i < size; ++i) record[RECORD + i] = b->aux_rx[(b->aux_head + i) % LIMIT];
        ssize_t n = write(b->backend, record, RECORD + size);
        if (n < 0) { if (!again()) return false; b->rx_retry = current + .01; }
        else if (n <= (ssize_t)RECORD || n > (ssize_t)(RECORD + size)) { errno = EIO; return false; }
        else { b->aux_head = (b->aux_head + (size_t)n - RECORD) % LIMIT; b->aux_size -= (size_t)n - RECORD; }
    }
    if (b->configuring) return true;
    uint8_t record[RECORD + PAYLOAD];
    ssize_t n = read(b->backend, record, sizeof(record));
    if (n < 0) { if (!again()) return false; }
    else {
        if (n < (ssize_t)RECORD || le16(record + 5) > PAYLOAD || n != (ssize_t)(RECORD + le16(record + 5))) {
            errno = EPROTO; return false;
        }
        size_t size = le16(record + 5);
        if (record[0] == 2 && size == 4) {
            b->baud = le32(record + RECORD);
            if (b->online && !configure_aux(b, b->baud)) return false;
        } else if (record[0] == 1 && size && b->online) {
            b->tx_epoch = le32(record + 1); b->tx_count = (unsigned)size;
            b->tx_busy = true; b->tx_deadline = INFINITY;
            if (!queue_aux(b, record + RECORD, size)) return false;
        } else { errno = EPROTO; return false; }
    }
    if (b->online && b->needs_config && !b->configuring && !b->tx_busy)
        return configure_aux(b, b->baud);
    return true;
}
static int open_uart(const char *path)
{
    int fd = open(path, O_RDWR | O_NOCTTY | O_NONBLOCK | O_CLOEXEC);
    if (fd < 0) return -1;
    struct termios term;
    if (flock(fd, LOCK_EX | LOCK_NB) < 0 || tcgetattr(fd, &term) < 0) goto fail;
    cfmakeraw(&term);
    term.c_cflag = (term.c_cflag & ~(CSIZE | PARENB | CSTOPB | CRTSCTS)) | CS8 | CREAD | CLOCAL;
    term.c_cc[VMIN] = term.c_cc[VTIME] = 0;
    if (cfsetispeed(&term, B115200) < 0 || cfsetospeed(&term, B115200) < 0 ||
        tcsetattr(fd, TCSANOW, &term) < 0 || tcflush(fd, TCIFLUSH) < 0) goto fail;
    return fd;
fail:
    { int error = errno; close(fd); errno = error; return -1; }
}
static bool transmit(struct broker *b)
{
    if (!b->active) {
        bool aux_ready = b->aux_tx.head && now() >= b->aux_ready;
        if (b->display_tx.head && (!b->turn || !aux_ready)) b->active = pop(&b->display_tx);
        else if (aux_ready) b->active = pop(&b->aux_tx);
        else return true;
        b->turn = 1 - b->turn;
    }
    struct frame *f = b->active;
    if (f->kind == DRAIN) {
        /* FIFO barrier for the UI: all earlier display packets were handed
         * to this physical UART. Wait for kernel TX completion before ACK. */
        bool ok = tcdrain(b->uart) == 0;
        const uint8_t ack = 0;
        if (ok && b->client >= 0)
            ok = append(&b->display_rx, &ack, 1, DRAIN, false);
        b->active = NULL;
        free(f);
        return ok;
    }
    ssize_t n = write(b->uart, f->data + f->offset, f->size - f->offset);
    if (n < 0) return again();
    f->offset += (size_t)n;
    if (f->offset != f->size) return true;
    b->active = NULL;
    bool ok = true;
    if (f->kind == PROBE) b->probe_deadline = now() + 1;
    else if (f->kind == BAUD) {
        uint8_t ready = 1;
        ok = control(b, 4, 0, &ready, 1);
        if (ok) { b->configuring = false; b->tty_ready = true; }
    } else if (f->kind == AUX) {
        int queued = 0;
        if (ioctl(b->uart, TIOCOUTQ, &queued) < 0) ok = false;
        else {
            b->aux_ready = now() + (f->size + (double)queued) * 10 / 115200 + (f->size - 6) * 10.0 / b->baud;
            if (f->last) b->tx_deadline = b->aux_ready;
        }
    }
    free(f);
    return ok;
}
static bool response(struct broker *b, const uint8_t *data, size_t size)
{
    if (data[1] == 0 && size == 8 && data[2] == 'O' && data[3] == 'K') {
        if (!b->online) { b->needs_config = true; b->tty_ready = false; }
        b->online = true; b->probe_deadline = 0;
    }
    if (data[1] == 0x3a) {
        if (b->online) {
            size_t length = data[2];
            if (length > LIMIT - b->aux_size) { errno = ENOBUFS; return false; }
            for (size_t i = 0; i < length; ++i) b->aux_rx[(b->aux_head + b->aux_size + i) % LIMIT] = data[3 + i];
            b->aux_size += length;
        }
    } else if (b->client >= 0 && !append(&b->display_rx, data, size, DISPLAY, false)) return false;
    return true;
}
static bool receive_uart(struct broker *b)
{
    if (b->rx_size >= sizeof(b->rx)) { errno = ENOBUFS; return false; }
    ssize_t n = read(b->uart, b->rx + b->rx_size, sizeof(b->rx) - b->rx_size);
    if (n < 0) return again();
    b->rx_size += (size_t)n;
    size_t used = 0;
    while (used < b->rx_size) {
        uint8_t *p = b->rx + used;
        size_t available = b->rx_size - used, payload = 0;
        if (p[0] != 0xaa) { ++used; continue; }
        if (available < 2) break;
        switch (p[1]) {
        case 0: payload = 2; break;
        case 0x31: payload = 3; break;
        case 0x32: if (available < 6) goto partial; payload = 4 + p[5]; break;
        case 0x33: case 0x34: payload = 2; break;
        case 0x3a: if (available < 3) goto partial; payload = 1 + p[2]; break;
        case 0xff: payload = 1; break;
        default: ++used; continue;
        }
        size_t total = payload + 6;
        if (available < total) break;
        if (memcmp(p + total - sizeof(tail), tail, sizeof(tail))) { ++used; continue; }
        if (!response(b, p, total)) return false;
        used += total;
    }
partial:
    if (used) { b->rx_size -= used; memmove(b->rx, b->rx + used, b->rx_size); }
    return true;
}
static void accept_client(struct broker *b)
{
    int fd = accept4(b->listener, NULL, NULL, SOCK_NONBLOCK | SOCK_CLOEXEC);
    if (fd < 0) return;
    if (b->client >= 0 || !b->online) { close(fd); return; }
    b->client = fd;
    if (!append(&b->display_rx, (const uint8_t *)"DWIN1", 5, DISPLAY, false)) drop_client(b);
}
static void client_events(struct broker *b, short events)
{
    if (events & (POLLERR | POLLHUP | POLLNVAL)) { drop_client(b); return; }
    if (events & POLLIN) {
        uint8_t data[PAYLOAD + 7];
        ssize_t n = recv(b->client, data, sizeof(data), MSG_TRUNC);
        if (n <= 0) { if (!n || !again()) drop_client(b); return; }
        if (n == 1 && data[0] == 0) {
            /* Transport-only drain request; never forward to the panel. */
            if (!append(&b->display_tx, data, 1, DRAIN, false))
                drop_client(b);
        } else if (n < 6 || n > (ssize_t)(PAYLOAD + 6) || data[0] != 0xaa ||
                   data[1] == 0x38 || data[1] == 0x39 ||
                   memcmp(data + n - 4, tail, sizeof(tail)) ||
                   !append(&b->display_tx, data, (size_t)n, DISPLAY, false)) {
            drop_client(b); return;
        }
    }
    if ((events & POLLOUT) && b->display_rx.head) {
        struct frame *f = b->display_rx.head;
        ssize_t n = send(b->client, f->data, f->size, MSG_NOSIGNAL);
        if (n < 0 && again()) return;
        if (n != (ssize_t)f->size) { drop_client(b); return; }
        free(pop(&b->display_rx));
    }
}
static void shorten(double deadline, double current, double *wait)
{
    if (deadline > current && isfinite(deadline) && deadline - current < *wait) *wait = deadline - current;
}
static void loop(struct broker *b)
{
    while (!stopping) {
        double current = now();
        if (b->uart < 0 && current >= b->uart_retry) {
            b->uart = open_uart(b->port_path);
            if (b->uart < 0) b->uart_retry = current + 1;
            else b->probe_at = 0;
        }
        if (b->uart >= 0) {
            if (b->probe_deadline && current >= b->probe_deadline) {
                errno = ETIMEDOUT; disconnect_transport(b, "panel handshake");
            } else if (current >= b->probe_at) {
                const uint8_t probe[] = {0xaa, 0, 0xcc, 0x33, 0xc3, 0x3c};
                if (!append(&b->display_tx, probe, sizeof(probe), PROBE, false)) { disconnect_transport(b, "probe queue"); continue; }
                b->probe_at = current + 2;
            }
        }
        if (!backend_tick(b)) { disconnect_transport(b, "kernel backend"); continue; }
        struct pollfd fds[] = {
            {b->listener, POLLIN, 0}, {b->client, POLLIN | (b->display_rx.head ? POLLOUT : 0), 0},
            {b->uart, POLLIN | ((b->active || b->display_tx.head || (b->aux_tx.head && current >= b->aux_ready)) ? POLLOUT : 0), 0},
            {b->backend, (!b->tx_busy && !b->configuring ? POLLIN : 0) |
                (!b->tx_busy && b->tty_ready && b->aux_size && current >= b->rx_retry ? POLLOUT : 0), 0}
        };
        double wait = .1;
        if (b->uart >= 0) { shorten(b->probe_at, current, &wait); shorten(b->probe_deadline, current, &wait); }
        else shorten(b->uart_retry, current, &wait);
        if (b->backend < 0) shorten(b->backend_retry, current, &wait);
        if (b->aux_tx.head) shorten(b->aux_ready, current, &wait);
        if (b->tx_busy) shorten(b->tx_deadline, current, &wait);
        if (b->aux_size) shorten(b->rx_retry, current, &wait);
        int result = poll(fds, sizeof(fds) / sizeof(fds[0]), (int)ceil(wait * 1000));
        if (result < 0) { if (errno == EINTR) continue; report("poll"); break; }
        if (fds[0].revents & POLLIN) accept_client(b);
        if (b->client >= 0 && fds[1].fd == b->client && fds[1].revents) client_events(b, fds[1].revents);
        if (b->uart >= 0 && fds[2].fd == b->uart) {
            if ((fds[2].revents & (POLLERR | POLLHUP | POLLNVAL)) ||
                ((fds[2].revents & POLLIN) && !receive_uart(b)) ||
                ((fds[2].revents & POLLOUT) && !transmit(b))) {
                if (!errno) errno = EIO;
                disconnect_transport(b, "physical UART");
                continue;
            }
        }
        if (b->backend >= 0 && fds[3].fd == b->backend && (fds[3].revents & (POLLERR | POLLHUP | POLLNVAL))) {
            errno = EIO; disconnect_transport(b, "kernel backend disconnected");
        }
    }
}
int main(int argc, char **argv)
{
    struct broker *b = calloc(1, sizeof(*b));
    if (!b) { report("allocation"); return 1; }
    b->listener = b->uart = b->client = b->backend = -1;
    b->baud = 115200; b->needs_config = true;
    b->socket_path = "/run/petrel-dwin/display.sock";
    b->backend_path = "/dev/dwin-uart-backend";
    const struct option options[] = {{"port", required_argument, NULL, 'p'},
        {"socket", required_argument, NULL, 's'}, {"backend", required_argument, NULL, 'b'},
        {"help", no_argument, NULL, 'h'}, {NULL, 0, NULL, 0}};
    int opt;
    while ((opt = getopt_long(argc, argv, "", options, NULL)) != -1) {
        if (opt == 'p') b->port_path = optarg;
        else if (opt == 's') b->socket_path = optarg;
        else if (opt == 'b') b->backend_path = optarg;
        else {
            FILE *out = opt == 'h' ? stdout : stderr;
            fprintf(out, "Usage: %s --port DEVICE [--backend DEVICE] [--socket PATH]\n", argv[0]);
            free(b); return opt == 'h' ? 0 : 2;
        }
    }
    if (!b->port_path || optind != argc) { fprintf(stderr, "--port is required; no positional arguments accepted\n"); free(b); return 2; }
    struct sockaddr_un address = {.sun_family = AF_UNIX};
    if (strlen(b->socket_path) >= sizeof(address.sun_path)) { fprintf(stderr, "Socket path too long\n"); free(b); return 2; }
    strcpy(address.sun_path, b->socket_path);
    b->listener = socket(AF_UNIX, SOCK_SEQPACKET | SOCK_NONBLOCK | SOCK_CLOEXEC, 0);
    if (b->listener < 0 || bind(b->listener, (struct sockaddr *)&address, sizeof(address)) < 0) {
        report("bind display socket (existing paths are never removed)"); close_fd(&b->listener); free(b); return 1;
    }
    if (chmod(b->socket_path, 0660) < 0 || listen(b->listener, 2) < 0) {
        report("listen"); close_fd(&b->listener); unlink(b->socket_path); free(b); return 1;
    }
    struct sigaction action = {.sa_handler = stop_signal};
    sigemptyset(&action.sa_mask);
    sigaction(SIGTERM, &action, NULL); sigaction(SIGINT, &action, NULL);
    signal(SIGPIPE, SIG_IGN);
    loop(b);
    disconnect_transport(b, NULL);
    close_fd(&b->listener);
    unlink(b->socket_path);
    free(b);
    return stopping ? 0 : 1;
}
