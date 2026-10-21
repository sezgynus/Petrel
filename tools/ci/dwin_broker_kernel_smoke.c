/* Reuse the real TTY client contract, but let the C broker own the backend. */
#define main direct_backend_smoke_main
#include "dwin_tty_smoke.c"
#undef main
#include <pty.h>
#include <signal.h>
#include <sys/socket.h>
#include <sys/un.h>

int main(void)
{
    int master, slave, status, child_status = 1;
    char path[128];
    check_device_identity();
    CHECK(openpty(&master, &slave, path, NULL, NULL) == 0);
    CHECK(fcntl(master, F_SETFL, O_NONBLOCK) == 0);
    pid_t broker = fork();
    CHECK(broker >= 0);
    if (!broker) {
        close(master);
        close(slave);
        execl("/broker", "broker", "--port", path, "--socket", "/display.sock", (char *)NULL);
        _exit(127);
    }
    unsigned char buffer[4096];
    size_t used = 0;
    int echoed = 0, configured = 0, saw_19200 = 0;
    pid_t tty_client = -1;
    for (int iteration = 0; iteration < 1000 && echoed < 1024; ++iteration) {
        struct pollfd p = {master, POLLIN, 0};
        CHECK(waitpid(broker, &status, WNOHANG) == 0);
        if (poll(&p, 1, 50) != 1 || !(p.revents & POLLIN)) continue;
        ssize_t n = read(master, buffer + used, sizeof(buffer) - used);
        if (n < 0 && (errno == EAGAIN || errno == EIO)) continue;
        CHECK(n > 0);
        used += n;
        size_t consumed = 0;
        while (used - consumed >= 6) {
            unsigned char *frame = buffer + consumed;
            CHECK(frame[0] == 0xaa);
            size_t end;
            for (end = 2; end + 4 <= used - consumed; ++end)
                if (memcmp(frame + end, "\xcc\x33\xc3\x3c", 4) == 0) break;
            if (end + 4 > used - consumed) break;
            if (frame[1] == 0) {
                const unsigned char reply[] = {0xaa, 0, 'O', 'K', 0xcc, 0x33, 0xc3, 0x3c};
                CHECK(write(master, reply, sizeof(reply)) == sizeof(reply));
            } else if (frame[1] == 0x38) {
                CHECK(end == 4);
                configured = 1;
                if (frame[2] == 3 && frame[3] == 0x30) saw_19200 = 1;
            } else {
                CHECK(frame[1] == 0x39 && end > 2 && end - 2 <= 248);
                unsigned char reply[255] = {0xaa, 0x3a, (unsigned char)(end - 2)};
                memcpy(reply + 3, frame + 2, end - 2);
                memcpy(reply + 1 + end, "\xcc\x33\xc3\x3c", 4);
                CHECK(write(master, reply, end + 5) == (ssize_t)(end + 5));
                echoed += end - 2;
            }
            consumed += end + 4;
        }
        used -= consumed;
        memmove(buffer, buffer + consumed, used);
        if (configured && tty_client < 0) {
            close(slave);
            usleep(100000); /* Allow the transmitted baud command's READY record. */
            tty_client = fork();
            CHECK(tty_client >= 0);
            if (!tty_client) { close(master); client(); }
        }
    }
    CHECK(echoed == 1024 && saw_19200 && tty_client > 0);
    usleep(200000); /* Final serialization ACK, then hang up via broker shutdown. */
    CHECK(kill(broker, SIGTERM) == 0);
    CHECK(waitpid(broker, &status, 0) == broker && WIFEXITED(status) && WEXITSTATUS(status) == 0);
    CHECK(waitpid(tty_client, &child_status, 0) == tty_client);
    CHECK(WIFEXITED(child_status) && WEXITSTATUS(child_status) == 0);
    CHECK(access("/display.sock", F_OK) < 0);
    close(master);
    puts("DWIN_C_KERNEL_PASS");
    return 0;
}
