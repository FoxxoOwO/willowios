#pragma once
/*
 * Per-board hardware constants for Enxerto.
 *
 * Build with -DBOARD_WILLOW (default in willowios), -DBOARD_TOPAZ, -DBOARD_SWEET,
 * or -DBOARD_BERYLLIUM.
 *
 * Xiaomi Redmi Note 8T (willow, SM6125 "trinket"):
 *   - 4x Kryo 260 Silver (0x0..0x3) + 4x Kryo 260 Gold (0x100..0x103)
 *   - 4 GB DDR at 0x40000000..0x140000000 (clean low DDR above ramoops: 0x62000000..0x80000000)
 *   - Splash framebuffer at 0x5c000000 (1080x2340x4, stride 4320)
 *   - Internal storage: sdhci@4744000 eMMC 5.1 (512-byte sectors)
 *   - USB: DWC3 @ 0x04e00000, QSCRATCH @ 0x04ef8800, QUSB2 v1 PHY @ 0x01613000,
 *          GCC @ 0x01400000, apps_smmu @ 0x0c600000 (stream ID 0x100)
 *   - PMIC: SPMI @ 0x01c40000, PM6125 (SID 0) PON 0x008 + GPIO5 0x0c4, PMI632 (SID 2) QG 0x4800 + SMB5 0x1000
 */
#if !defined(BOARD_BERYLLIUM) && !defined(BOARD_SWEET) && !defined(BOARD_TOPAZ) && !defined(BOARD_WILLOW)
#define BOARD_WILLOW 1
#endif

#if defined(BOARD_WILLOW)

#define BOARD_NAME		"willow"
#define BOARD_BLURB		"Enxerto · Redmi Note 8T (willow)"

/* reserved-memory cont_splash_region @ 0x5c000000 (1080x2340 BGRX8888) */
#define FB_BASE			0x5c000000UL
#define FB_PHYS			FB_BASE
#define FB_W			1080
#define FB_H			2340
#define FB_STRIDE		(FB_W * 4)

/* intc@f200000 (GICv3, stride 0x20000) */
#define GICD_BASE		0x0f200000UL
#define GICR_BASE		0x0f300000UL
#define GICR_SIZE		0x100000UL
#define GICR_PE_SIZE		0x20000UL

/* MPM2_MPM_PS_HOLD & IMEM restart_reason (trinket.dtsi) */
#define PSHOLD			0x0440b000UL
#define PSHOLD_ADDR		PSHOLD
#define IMEM_RESTART_REASON	0x0c12565cUL
#define RESTART_REASON_ADDR	IMEM_RESTART_REASON

/* sdhci@4744000 eMMC 5.1 (trinket.dtsi) */
#define BOARD_SDHCI		1
#define SDHCI_BASE		0x04744000UL
#define SDHCI_CMDQ_BASE		0x04745000UL
#define UFS_BASE		0x04804000UL

/* ssusb@4e00000 -> dwc3@4e00000, qusb@1613000 (major-rev 1), gcc@1400000, apps-smmu@c600000 */
#define GCC_BASE		0x01400000UL
#define DWC3_BASE		0x04e00000UL
#define QSCRATCH_BASE		0x04ef8800UL
#define QUSB2_BASE		0x01613000UL
#define QUSB2_MAJOR_REV		1
#define SMMU_BASE		0x0c600000UL
#define SMMU_SID		0x100u

/* qcom,spmi-pmic-arb @ 0x01c40000 (trinket.dtsi); PM6125 SID 0 + PMI632 SID 2 (QG @ 0x4800) */
#define SPMI_CORE_BASE		0x01c40000UL
#define SPMI_CHNL_BASE		0x01e00000UL
#define SPMI_OBS_BASE		0x03e00000UL
#define SPMI_CNFG_BASE		0x01c0a000UL
#define PMIC_HAS_QG		1
#define ENXERTO_CHARGER		0	/* PMI632 SMB5: do not write PMI8998 SMB2 registers */
#define KEYS_GPIO_PPID		0x0c4u
#define KEYS_GPIO_RT		0xc410u

/*
 * willow (SM6125 "trinket"): ABL runs on cpu0 (Kryo 260 Silver, MPIDR 0x0), which has no 16 KiB
 * MMU granule. Cpu4 (Kryo 260 Gold, MPIDR 0x100) has 16 KiB pages: hop to it via PSCI CPU_ON.
 */
#define BOARD_GOLD_HANDOFF	1
#define BOARD_GOLD_MPIDR	0x100UL
#define BOARD_GOLD_GICR_SLOT	4u
#define BOARD_GOLD_OSM_BASE	0x0f523000UL	/* qcom,clk-cpu-osm-trinket perfcl */

/*
 * Fastboot download + storage scratch window on willow (4 GB DDR 0x40000000..0x140000000):
 * All Qualcomm carve-outs end at 0x61a00000 (ramoops@61600000), and XNU's RAM starts at 0x80000000.
 * Place the fastboot download + 4 MiB scratch window at 0x62000000..0x80000000 (480 MiB total).
 */
#define DL_BASE			0x62000000UL
#define DL_SIZE			0x1e000000UL

#elif defined(BOARD_TOPAZ)

#define BOARD_NAME		"topaz"
#define BOARD_BLURB		"Enxerto · Redmi Note 12 4G"

#define FB_BASE			0x5c000000UL
#define FB_PHYS			FB_BASE
#define FB_W			1080
#define FB_H			2400
#define FB_STRIDE		(FB_W * 4)

#define GICD_BASE		0x0f200000UL
#define GICR_BASE		0x0f300000UL
#define GICR_SIZE		0x100000UL
#define GICR_PE_SIZE		0x20000UL

#define PSHOLD			0x0440b000UL
#define PSHOLD_ADDR		PSHOLD
#define IMEM_RESTART_REASON	0x0c12565cUL
#define RESTART_REASON_ADDR	IMEM_RESTART_REASON

#define UFS_BASE		0x04804000UL

#define GCC_BASE		0x01400000UL
#define DWC3_BASE		0x04e00000UL
#define QSCRATCH_BASE		0x04ef8800UL
#define QUSB2_BASE		0x01613000UL
#define QUSB2_MAJOR_REV		1
#define SMMU_BASE		0x0c600000UL
#define SMMU_SID		0x100u

#define SPMI_CORE_BASE		0x01c40000UL
#define SPMI_CHNL_BASE		0x02000000UL
#define SPMI_OBS_BASE		0x03e00000UL
#define SPMI_CNFG_BASE		0x01c0a000UL
#define PMIC_HAS_QG		1
#define KEYS_GPIO_PPID		0x0c4u
#define KEYS_GPIO_RT		0xc410u

#define BOARD_GOLD_HANDOFF	1
#define BOARD_GOLD_MPIDR	0x100UL
#define BOARD_GOLD_GICR_SLOT	4u
#define BOARD_GOLD_OSM_BASE	0x0f523000UL

#define DL_BASE			0xb8000000UL
#define DL_SIZE			0x40000000UL

#elif defined(BOARD_BERYLLIUM)

#define BOARD_NAME		"beryllium"
#define BOARD_BLURB		"Enxerto · Poco F1"

#define FB_BASE			0x9d400000UL
#define FB_PHYS			FB_BASE
#define FB_W			1080
#define FB_H			2246
#define FB_STRIDE		(FB_W * 4)

#define GICD_BASE		0x17a00000UL
#define GICR_BASE		0x17a60000UL
#define GICR_SIZE		0x100000UL
#define GICR_PE_SIZE		0x20000UL

#define PSHOLD			0x0c264000UL
#define PSHOLD_ADDR		PSHOLD
#define IMEM_RESTART_REASON	0x146bf65cUL
#define RESTART_REASON_ADDR	IMEM_RESTART_REASON

#define UFS_BASE		0x01d84000UL

#define GCC_BASE		0x00100000UL
#define DWC3_BASE		0x0a600000UL
#define QSCRATCH_BASE		0x0a6f8800UL
#define QUSB2_BASE		0x088e2000UL
#define QUSB2_MAJOR_REV		2
#define SMMU_BASE		0x15000000UL
#define SMMU_SID		0x740u

#define SPMI_CORE_BASE		0x0c440000UL
#define SPMI_CHNL_BASE		0x0c600000UL
#define SPMI_OBS_BASE		0x0e600000UL
#define SPMI_CNFG_BASE		0x0c40a000UL
#define PMIC_HAS_QG		0
#define KEYS_GPIO_PPID		0x0c5u
#define KEYS_GPIO_RT		0xc510u

#define BOARD_GOLD_HANDOFF	0

#define DL_BASE			0xb8000000UL
#define DL_SIZE			0x40000000UL

#else /* BOARD_SWEET */

#define BOARD_NAME		"sweet"
#define BOARD_BLURB		"Enxerto · Redmi Note 10 Pro"

#define FB_BASE			0x9c000000UL
#define FB_PHYS			FB_BASE
#define FB_W			1080
#define FB_H			2400
#define FB_STRIDE		(FB_W * 4)

#define GICD_BASE		0x17a00000UL
#define GICR_BASE		0x17a60000UL
#define GICR_SIZE		0x100000UL
#define GICR_PE_SIZE		0x20000UL

#define PSHOLD			0x0c264000UL
#define PSHOLD_ADDR		PSHOLD
#define IMEM_RESTART_REASON	0x146aa65cUL
#define RESTART_REASON_ADDR	IMEM_RESTART_REASON

#define UFS_BASE		0x01d84000UL

#define GCC_BASE		0x00100000UL
#define DWC3_BASE		0x0a600000UL
#define QSCRATCH_BASE		0x0a6f8800UL
#define QUSB2_BASE		0x088e2000UL
#define QUSB2_MAJOR_REV		2
#define SMMU_BASE		0x15000000UL
#define SMMU_SID		0x740u

#define SPMI_CORE_BASE		0x0c440000UL
#define SPMI_CHNL_BASE		0x0c600000UL
#define SPMI_OBS_BASE		0x0e600000UL
#define SPMI_CNFG_BASE		0x0c40a000UL
#define PMIC_HAS_QG		0
#define KEYS_GPIO_PPID		0x4c1u
#define KEYS_GPIO_RT		0xc110u

#define BOARD_GOLD_HANDOFF	0

#define DL_BASE			0xb8000000UL
#define DL_SIZE			0x40000000UL

#endif
