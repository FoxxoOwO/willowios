/*
 * Milestone 5 probe for Xiaomi Redmi Note 8T (willow, SM6125 "trinket"):
 * talk to internal eMMC 5.1 on sdhci@4744000 (qcom,sdhci-msm-v5) that ABL
 * booted from (with fallback probe for ufshc@4804000).
 *
 * Runs with the MMU off (all memory Device). Uses READ-ONLY polled PIO
 * commands (CMD17/CMD18) over the 512-byte sector eMMC bus left in Transfer
 * State by ABL. Nothing is ever written to the device.
 */
#include <stdint.h>
#include "console.h"
#include "ufs.h"

#define SDHCI_BASE		0x04744000UL	/* sdhci@4744000 hc_mem on willow */
#define SDHCI_CMDQ_BASE		0x04745000UL	/* sdhci@4744000 cmdq_mem on willow */

#define SDHCI_DMA_ADDRESS	0x00
#define SDHCI_BLOCK_SIZE	0x04		/* 16-bit: [11:0] blk size */
#define SDHCI_BLOCK_COUNT	0x06		/* 16-bit */
#define SDHCI_ARGUMENT		0x08
#define SDHCI_TRANSFER_MODE	0x0c		/* 16-bit */
#define SDHCI_COMMAND		0x0e		/* 16-bit */
#define SDHCI_RESPONSE		0x10
#define SDHCI_BUFFER		0x20
#define SDHCI_PRESENT_STATE	0x24
#define SDHCI_HOST_CONTROL	0x28
#define SDHCI_CLOCK_CONTROL	0x2c
#define SDHCI_SOFTWARE_RESET	0x2f
#define SDHCI_INT_STATUS	0x30
#define SDHCI_INT_ENABLE	0x34
#define SDHCI_SIGNAL_ENABLE	0x38
#define SDHCI_HOST_CONTROL2	0x3e
#define SDHCI_CAPABILITIES	0x40
#define SDHCI_CAPABILITIES_1	0x44
#define SDHCI_HOST_VERSION	0xfe

#define SDHCI_CMD_INHIBIT	0x00000001U
#define SDHCI_DATA_INHIBIT	0x00000002U
#define SDHCI_DATA_AVAILABLE	0x00000800U

#define SDHCI_TRNS_BLK_CNT_EN	0x0002U
#define SDHCI_TRNS_AUTO_CMD12	0x0004U
#define SDHCI_TRNS_READ		0x0010U
#define SDHCI_TRNS_MULTI	0x0020U

#define SDHCI_INT_RESPONSE	0x00000001U
#define SDHCI_INT_DATA_END	0x00000002U
#define SDHCI_INT_DATA_AVAIL	0x00000020U
#define SDHCI_INT_ERROR		0x00008000U

#define EMMC_SECTOR		512U
#define BLOCK			4096U

static inline uint32_t sdhci_rd32(uint32_t off)
{
	return *(volatile uint32_t *)(SDHCI_BASE + off);
}

static inline uint16_t sdhci_rd16(uint32_t off)
{
	return *(volatile uint16_t *)(SDHCI_BASE + off);
}

static inline void sdhci_wr32(uint32_t off, uint32_t v)
{
	*(volatile uint32_t *)(SDHCI_BASE + off) = v;
}

static inline void sdhci_wr16(uint32_t off, uint16_t v)
{
	*(volatile uint16_t *)(SDHCI_BASE + off) = v;
}

static inline void sdhci_wr8(uint32_t off, uint8_t v)
{
	*(volatile uint8_t *)(SDHCI_BASE + off) = v;
}

static uint8_t data[4 * BLOCK] __attribute__((aligned(4096)));

static uint64_t ticks(void)
{
	uint64_t t;
	__asm__ volatile("isb; mrs %0, cntvct_el0" : "=r"(t));
	return t;
}

static uint32_t le32(const uint8_t *p)
{
	return (uint32_t)p[0] | ((uint32_t)p[1] << 8) | ((uint32_t)p[2] << 16) | ((uint32_t)p[3] << 24);
}

static uint64_t le64(const uint8_t *p)
{
	return (uint64_t)le32(p) | ((uint64_t)le32(p + 4) << 32);
}

static void sdhci_reset_lines(uint8_t mask)
{
	sdhci_wr8(SDHCI_SOFTWARE_RESET, mask);
	uint64_t start = ticks();
	while (sdhci_rd32(SDHCI_CLOCK_CONTROL) & ((uint32_t)mask << 24)) {
		if (ticks() - start > 1920000)
			break;
	}
}

/*
 * Read `cnt` 512-byte sectors starting at 512B LBA `sector` via polled PIO.
 * Returns 0 on success, non-zero stage code on error.
 */
static uint32_t emmc_read_sectors(uint32_t sector, uint32_t cnt, void *buf)
{
	uint32_t *dst = (uint32_t *)buf;
	uint64_t start = ticks();

	while (sdhci_rd32(SDHCI_PRESENT_STATE) & (SDHCI_CMD_INHIBIT | SDHCI_DATA_INHIBIT)) {
		if (ticks() - start > 19200000) {
			sdhci_reset_lines(0x06);
			return 1;
		}
	}

	/* Ensure CQE is off and status bits are enabled (polled, no IRQs) */
	uint32_t cqcfg = *(volatile uint32_t *)(SDHCI_CMDQ_BASE + 0x08);
	if (cqcfg & 1U)
		*(volatile uint32_t *)(SDHCI_CMDQ_BASE + 0x08) = cqcfg & ~1U;

	sdhci_wr32(SDHCI_SIGNAL_ENABLE, 0);
	sdhci_wr32(SDHCI_INT_ENABLE, 0x03ff00fbU);
	sdhci_wr32(SDHCI_INT_STATUS, 0xffffffffU);

	/* Clear DMA bits in HOST_CONTROL and HOST_CONTROL2 for pure PIO */
	uint8_t hctrl = *(volatile uint8_t *)(SDHCI_BASE + SDHCI_HOST_CONTROL);
	sdhci_wr8(SDHCI_HOST_CONTROL, hctrl & ~0x18U);
	uint16_t hc2 = sdhci_rd16(SDHCI_HOST_CONTROL2);
	sdhci_wr16(SDHCI_HOST_CONTROL2, hc2 & ~(1U << 12));

	sdhci_wr32(SDHCI_BLOCK_SIZE, EMMC_SECTOR | ((cnt & 0xffffU) << 16));
	sdhci_wr32(SDHCI_ARGUMENT, sector);

	uint16_t mode = SDHCI_TRNS_READ | SDHCI_TRNS_BLK_CNT_EN;
	uint16_t cmd_idx = 17;
	if (cnt > 1) {
		mode |= SDHCI_TRNS_MULTI | SDHCI_TRNS_AUTO_CMD12;
		cmd_idx = 18;
	}
	uint16_t cmd = (uint16_t)((cmd_idx << 8) | 0x3aU); /* DATA | INDEX | CRC | R1(48) */
	sdhci_wr32(SDHCI_TRANSFER_MODE, (uint32_t)mode | ((uint32_t)cmd << 16));

	start = ticks();
	while (!(sdhci_rd32(SDHCI_INT_STATUS) & SDHCI_INT_RESPONSE)) {
		if (sdhci_rd32(SDHCI_INT_STATUS) & SDHCI_INT_ERROR) {
			sdhci_reset_lines(0x06);
			return 2;
		}
		if (ticks() - start > 19200000) {
			sdhci_reset_lines(0x06);
			return 3;
		}
	}
	sdhci_wr32(SDHCI_INT_STATUS, SDHCI_INT_RESPONSE);

	for (uint32_t s = 0; s < cnt; s++) {
		start = ticks();
		while (!(sdhci_rd32(SDHCI_PRESENT_STATE) & SDHCI_DATA_AVAILABLE) &&
		       !(sdhci_rd32(SDHCI_INT_STATUS) & SDHCI_INT_DATA_AVAIL)) {
			if (sdhci_rd32(SDHCI_INT_STATUS) & SDHCI_INT_ERROR) {
				sdhci_reset_lines(0x06);
				return 4;
			}
			if (ticks() - start > 19200000) {
				sdhci_reset_lines(0x06);
				return 5;
			}
		}
		sdhci_wr32(SDHCI_INT_STATUS, SDHCI_INT_DATA_AVAIL);
		for (unsigned w = 0; w < EMMC_SECTOR / 4; w++)
			*dst++ = sdhci_rd32(SDHCI_BUFFER);
	}

	start = ticks();
	while (!(sdhci_rd32(SDHCI_INT_STATUS) & SDHCI_INT_DATA_END)) {
		if (sdhci_rd32(SDHCI_INT_STATUS) & SDHCI_INT_ERROR)
			break;
		if (ticks() - start > 19200000)
			break;
	}
	sdhci_wr32(SDHCI_INT_STATUS, 0xffffffffU);
	return 0;
}

static const char *fs_type_emmc(uint32_t sector512)
{
	if (emmc_read_sectors(sector512, 8, data))
		return "read error";
	const uint8_t *sb = data + 1024;
	if (sb[0] == 0x10 && sb[1] == 0x20 && sb[2] == 0xf5 && sb[3] == 0xf2)
		return "f2fs";
	if (sb[56] == 0x53 && sb[57] == 0xef)
		return "ext4";
	if (data[1024] == 'H' && (data[1025] == '+' || data[1025] == 'X'))
		return "hfs+";
	return "other";
}

static int str_eq(const char *a, const char *b)
{
	while (*a && *a == *b)
		a++, b++;
	return *a == *b;
}

static void list_emmc_partitions(uint32_t entry_lba512, uint32_t nent)
{
	static uint8_t ents[128 * 128] __attribute__((aligned(4096)));
	uint32_t sectors = (nent * 128 + EMMC_SECTOR - 1) / EMMC_SECTOR;
	if (emmc_read_sectors(entry_lba512, sectors, ents)) {
		con_str("EMMC PT", "read error");
		return;
	}
	for (uint32_t i = 0; i < nent; i++) {
		const uint8_t *e = ents + i * 128;
		uint64_t first = le64(e + 32), last = le64(e + 40);
		if (!first)
			continue;
		char name[17];
		for (int c = 0; c < 16; c++) {
			uint8_t ch = e[56 + 2 * c];
			name[c] = (ch >= 32 && ch < 127) ? (char)ch : (ch ? '?' : 0);
		}
		name[16] = 0;
		uint64_t mib = (last - first + 1) >> 11; /* 512B sectors -> MiB */
		if (mib < 32)
			continue;
		con_hex2(name, "sec=", (uint32_t)first, "MiB=", (uint32_t)mib);
		if (str_eq(name, "userdata") || str_eq(name, "cust") ||
		    str_eq(name, "cache") || str_eq(name, "boot"))
			con_str(" fs", fs_type_emmc((uint32_t)first));
	}
}

void test_ufs(void)
{
	con_str("EMMC", "willow sdhci@4744000 probe (read-only)");
	uint32_t ver = sdhci_rd16(SDHCI_HOST_VERSION);
	uint32_t cap0 = sdhci_rd32(SDHCI_CAPABILITIES);
	uint32_t cap1 = sdhci_rd32(SDHCI_CAPABILITIES_1);
	uint32_t pstate = sdhci_rd32(SDHCI_PRESENT_STATE);
	uint32_t clk = sdhci_rd16(SDHCI_CLOCK_CONTROL);
	con_hex2("SDHCI", "ver=", ver, "pstate=", pstate);
	con_hex2("SDHCI", "cap0=", cap0, "cap1=", cap1);
	con_hex2("SDHCI", "clk=", clk, "int=", sdhci_rd32(SDHCI_INT_STATUS));

	/* Read first 8 sectors (4 KiB): LBA 0 (MBR) + LBA 1 (GPT header) */
	uint32_t rc = emmc_read_sectors(0, 8, data);
	con_hex2("EMMC RD", "rc=", rc, "sig=", data[510] | ((uint32_t)data[511] << 8));
	if (rc)
		return;

	const uint8_t *gpt = data + EMMC_SECTOR; /* 512-byte sector 1 */
	char sig[9];
	for (int i = 0; i < 8; i++)
		sig[i] = (gpt[i] >= 32 && gpt[i] < 127) ? (char)gpt[i] : '.';
	sig[8] = 0;
	con_str("EMMC GPT", sig);
	uint32_t nent = le32(gpt + 80), esz = le32(gpt + 84);
	uint32_t elba = (uint32_t)le64(gpt + 72);
	con_hex2("EMMC GPT", "entries=", nent, "lba=", elba);
	if (esz != 128 || nent > 128)
		return;
	list_emmc_partitions(elba, nent);
}
