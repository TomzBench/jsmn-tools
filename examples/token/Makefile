SHELL   := /bin/sh
BUILD   := build
CFLAGS  := -Os -Wall

# Crypto backend for the two mac hooks: openssl, mbedtls or psa
CRYPTO  ?= openssl
LDLIBS_openssl := -lcrypto
LDLIBS_mbedtls := -lmbedcrypto
LDLIBS_psa     := -lmbedcrypto

$(BUILD)/main: $(BUILD)/main.c
	$(CC) $(CFLAGS) -o $@ $< $(LDLIBS_$(CRYPTO))

$(BUILD)/main.c: main.c.jinja session.yaml
	jsmn render session.yaml --global token_crypto=$(CRYPTO) --template $< $@

.PHONY: run clean
run: $(BUILD)/main
	./$<

clean:
	rm -rf $(BUILD)
