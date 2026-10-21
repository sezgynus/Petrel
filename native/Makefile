CC ?= cc
CFLAGS ?= -Os
CFLAGS += -std=c11 -Wall -Wextra -Werror -Wformat=2 -fstack-protector-strong -D_FORTIFY_SOURCE=2
LDFLAGS ?=

.PHONY: all clean
all: petrel-dwin-broker

petrel-dwin-broker: dwin_broker.c
	$(CC) $(CFLAGS) $< $(LDFLAGS) -lm -o $@

clean:
	rm -f petrel-dwin-broker
