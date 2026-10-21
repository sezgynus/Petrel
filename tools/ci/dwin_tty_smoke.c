/* Real Linux TTY API contract, run only inside a disposable CI QEMU guest. */
#include <errno.h>
#include <fcntl.h>
#include <poll.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/ioctl.h>
#include <sys/stat.h>
#include <sys/wait.h>
#include <termios.h>
#include <unistd.h>

#define CHECK(x) do { if (!(x)) { perror(#x); exit(1); } } while (0)
static unsigned char msg[255];

static void check_attribute(const char *name, const char *expected)
{
    char path[256], value[128];
    struct stat st;
    snprintf(path, sizeof(path), "/sys/class/tty/ttyDWIN0/%s", name);
    CHECK(stat(path, &st) == 0 && S_ISREG(st.st_mode));
    CHECK((st.st_mode & 0222) == 0);
    int fd = open(path, O_RDONLY);
    CHECK(fd >= 0);
    ssize_t count = read(fd, value, sizeof(value) - 1);
    CHECK(count > 0);
    value[count] = '\0';
    CHECK(strcmp(value, expected) == 0);
    close(fd);
}

static void check_device_identity(void)
{
    char path[512];
    /* These are the exact paths consumed by Moonraker serial discovery. */
    check_attribute("uartclk", "15667200\n");
    check_attribute("port", "0x0\n");
    CHECK(realpath("/sys/class/tty/ttyDWIN0/device/driver", path) != NULL);
    CHECK(strcmp(path, "/sys/bus/dwin/drivers/dwin_uart") == 0);
    CHECK(realpath("/sys/class/tty/ttyDWIN0/device/subsystem", path) != NULL);
    CHECK(strcmp(path, "/sys/bus/dwin") == 0);
    CHECK(access("/sys/bus/dwin/drivers/dwin_uart/bind", F_OK) == -1);
    CHECK(access("/sys/bus/dwin/drivers/dwin_uart/unbind", F_OK) == -1);
    puts("DWIN_IDENTITY_PASS hardware_uart dwin_uart");
}

static void client(void)
{
    struct termios t;
    unsigned char tx[1024], rx[1024];
    size_t sent = 0, received = 0;
    int fd = open("/dev/ttyDWIN0", O_RDWR | O_NOCTTY);
    CHECK(fd >= 0);
    CHECK(tcgetattr(fd, &t) == 0);
    cfmakeraw(&t);
    t.c_cflag |= CLOCAL | CREAD;
    t.c_cc[VMIN] = 1;
    t.c_cc[VTIME] = 1;
    CHECK(cfsetispeed(&t, B19200) == 0);
    CHECK(cfsetospeed(&t, B19200) == 0);
    CHECK(tcsetattr(fd, TCSANOW, &t) == 0);
    CHECK(tcgetattr(fd, &t) == 0 && cfgetospeed(&t) == B19200);
    CHECK(cfsetispeed(&t, B9600) == 0);
    CHECK(cfsetospeed(&t, B9600) == 0);
    CHECK(tcsetattr(fd, TCSANOW, &t) == 0);
    CHECK(tcgetattr(fd, &t) == 0 && cfgetospeed(&t) == B19200);
    CHECK(tcflush(fd, TCIOFLUSH) == 0);
    for (size_t i = 0; i < sizeof(tx); ++i)
        tx[i] = (unsigned char)i;
    while (sent < sizeof(tx)) {
        ssize_t n = write(fd, tx + sent, sizeof(tx) - sent);
        CHECK(n > 0);
        sent += n;
    }
    CHECK(tcdrain(fd) == 0);
    while (received < sizeof(rx)) {
        struct pollfd p = {fd, POLLIN, 0};
        CHECK(poll(&p, 1, 3000) == 1);
        ssize_t n = read(fd, rx + received, sizeof(rx) - received);
        CHECK(n > 0);
        received += n;
    }
    CHECK(memcmp(tx, rx, sizeof(tx)) == 0);
    /* Backend failure must wake poll with HUP rather than a forever-open port. */
    struct pollfd p = {fd, POLLIN, 0};
    CHECK(poll(&p, 1, 5000) == 1 && (p.revents & POLLHUP));
    close(fd);
    exit(0);
}

int main(void)
{
    check_device_identity();
    int status = 1, echoed = 0;
    int backend = open("/dev/dwin-uart-backend", O_RDWR | O_NONBLOCK);
    CHECK(backend >= 0);
    unsigned char ready[] = {4, 0, 0, 0, 0, 1, 0, 1};
    CHECK(write(backend, ready, sizeof(ready)) == sizeof(ready));
    pid_t child = fork();
    CHECK(child >= 0);
    if (!child) {
        close(backend); /* Parent retains backend ownership. */
        client();
    }
    for (int iteration = 0; iteration < 200; ++iteration) {
        if (waitpid(child, &status, WNOHANG) == child)
            break;
        struct pollfd p = {backend, POLLIN, 0};
        if (poll(&p, 1, 100) != 1)
            continue;
        ssize_t count = read(backend, msg, sizeof(msg));
        CHECK(count >= 7);
        unsigned int length = msg[5] | (msg[6] << 8);
        CHECK(count == 7 + length);
        if (msg[0] == 2) {
            CHECK(length == 4);
        } else {
            CHECK(msg[0] == 1);
            CHECK(write(backend, msg, count) == count); /* TX -> RX echo. */
            unsigned char ack[] = {3, msg[1], msg[2], msg[3], msg[4], 4, 0,
                length & 255, length >> 8, 0, 0};
            CHECK(write(backend, ack, sizeof(ack)) == sizeof(ack));
            echoed += length;
            if (echoed == 1024) {
                usleep(100000);
                close(backend);
                CHECK(waitpid(child, &status, 0) == child);
                break;
            }
        }
    }
    CHECK(WIFEXITED(status) && WEXITSTATUS(status) == 0 && echoed == 1024);
    puts("DWIN_SMOKE_PASS");
    return 0;
}
