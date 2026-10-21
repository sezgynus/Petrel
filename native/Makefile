CC ?= cc
CFLAGS ?= -Os
CFLAGS += -std=c11 -Wall -Wextra -Werror -Wformat=2 -fstack-protector-strong -D_FORTIFY_SOURCE=2
LDFLAGS ?=
OUTPUT ?= petrel-dwin-broker

.PHONY: all clean
all: $(OUTPUT)

$(OUTPUT): dwin_broker.c
	$(CC) $(CFLAGS) $< $(LDFLAGS) -lm -o $@

clean:
	rm -f petrel-dwin-broker
