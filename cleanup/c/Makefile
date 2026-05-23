CC      ?= cc
CFLAGS  ?= -O2 -Wall -Wextra
BINDIR  := ../bin

.PHONY: all clean

all: $(BINDIR)/stat-hook

$(BINDIR):
	mkdir -p $@

$(BINDIR)/stat-hook: stat_hook.c | $(BINDIR)
	$(CC) $(CFLAGS) -o $@ $<

clean:
	rm -f $(BINDIR)/stat-hook
