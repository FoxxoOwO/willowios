# Stav a technická dokumentace projektu willowios (iOS 16 na Xiaomi Redmi Note 8T)

Dokument zachycuje kompletní popis, technickou architekturu, aktuální stav a detaily nativního portu operačního systému **Apple iOS 16 (Darwin / XNU)** na chytrý telefon **Xiaomi Redmi Note 8T** (`willow`).

---

## 1. Přehled a cíl projektu

* **Cíl projektu**: Nativní spuštění jádra Apple Darwin / XNU (`xnu-8796.141.3`, iOS 16.7.16 Build `20H392`) a plnohodnotného uživatelského grafického rozhraní iOS 16 (SpringBoard, backboardd, UIKit) na komerčním Android zařízení bez hardwarové emulace (bare-metal).
* **Cílové zařízení**: Xiaomi Redmi Note 8T (kódové označení `willow`, varianta `ginkgo` s NFC).
* **Základní filozofie**:
  * Žádná emulace – instrukce běží přímo na ARM64 jádrech SoC Qualcomm Snapdragon 665.
  * Zachování integrity telefonu – bootování probíhá přes dočasné obrazy pomocí `fastboot boot` (zavaděče XBL, ABL, partition table GPT a záchranné oddíly zůstávají netknuté).
  * Root filesystem iOS je umístěn v nativním oddílu `userdata` na interním eMMC úložišti (formát HFS+/APFS emulovaný blokovým rozhraním XNU).

---

## 2. Hardwarová specifikace zařízení (`willow`)

| Komponenta | Specifikace na zařízení `willow` | Stav integrace v XNU / iOS |
|---|---|---|
| **SoC** | Qualcomm Snapdragon 665 (`SM6125` / `trinket`) | Plně funkční (Kryo 260 Gold + Silver) |
| **CPU Architektura** | 8 jader: 4x Cortex-A73 (Gold) + 4x Cortex-A53 (Silver) | SMP běh, 16K/4K page tables |
| **Operační paměť** | 4 GiB LPDDR4x (`0x40000000..0x140000000`) | 3 GiB vyhrazeno pro XNU (`0x80000000..0x140000000`) |
| **Interní úložiště** | 64/128 GB eMMC 5.1 (SDHCI v5 na `0x04744000`) | Plně funkční (vlastní SDHCI polled driver v `sweet_ufs.c`) |
| **Displej / Panel** | Tianma / Shenchao FHD+ IPS LCD (1080 × 2340 @ 60 Hz) | Plně funkční continuous splash FB (`0x5c000000`) |
| **Dotyková vrstva** | Novatek NT36672A přes QUP0 SE2 GENI SPI (`0x04a88000`) | V řešení (hardware SPI + TLMM `0x00400000`, bootloader reset) |
| **Grafický akcelerátor** | Qualcomm Adreno 610 | Plně funkční (Mesa Freedreno 25.0.7, 60 FPS v CoreAnimation) |
| **PMIC / Baterie** | Qualcomm PMI632 přes SPMI (`0x01c40000`) | Ovladač `SweetBattery` a SPMI arbiter implementován |
| **USB / Konektivita** | DWC3 (`0x04e00000`) + QUSB2 v1 PHY (`0x01613000`) | Funkční USB CDC-ECM Ethernet a UDP konzolový streaming |

---

## 3. Softwarová a systémová architektura

```
+-------------------------------------------------------------------------+
|                              iOS 16 Userland                            |
|    SpringBoard (GUI)  <--->  backboardd  <--->  CoreAnimation (CA)     |
|              ^                    ^                                     |
|              |                    | (Mesa Freedreno GLES + Topaz-GL)    |
|       libtopaz-inject      libOSMesa.8.dylib                            |
|       (Auto-Unlock,        libtopaz-gl.dylib                            |
|        Anti-Crash hooks)   (Adreno 610 HW acceleration)                 |
+-------------------------------------------------------------------------+
|                        Apple XNU Kernel (Darwin 22.x)                   |
|  - BSD Subsystem, VFS, Mach IPC, VM Manager (16K/4K)                    |
|  - sweet_ufs.c: Qualcomm SDHCI MSM v5 eMMC blokový driver & GPT parser  |
|  - sweet_touch.c: QUP0 SE2 GENI SPI driver pro Novatek NT36672A         |
|  - sweetfb: Framebuffer 1080x2340@60Hz na 0x5c000000                   |
+-------------------------------------------------------------------------+
|                    XNU Payload & Apple Device Tree                      |
|  - payload.bin: XNU Kernel + willow.adt (obsahuje blobs.bin)            |
+-------------------------------------------------------------------------+
|                  Linux Shim Trampoline (EvolutionX kernel)              |
|  - Připraví hardware, nastaví hodiny, předá řízení XNU entrypointu      |
+-------------------------------------------------------------------------+
|                  Qualcomm ABL Bootloader (LinuxLoader.efi)              |
|  - Spuštěno dočasně přes: fastboot boot shim-evox-boot.img              |
+-------------------------------------------------------------------------+
```

### 3.1. Bootovací řetězec (Boot Pipeline)
1. **Fastboot Host**: PC odešle boot image pomocí `fastboot boot shim-evox-boot-guiXX.img`.
2. **Qualcomm ABL (`LinuxLoader.efi`)**: Zavaděč ověří hlavičku Android Boot Image v2 a nahraje Linux Shim kernel do paměti RAM (`0x40080000`).
3. **Linux Shim (EvolutionX Trinket Kernel)**: Slouží jako hardwarová trampolína. Inicializuje napájecí větve, základní takty sběrnic, paměťový řadič a skočí do připojeného XNU Payloadu.
4. **XNU Payload (`mkpayload.py`)**: Rozbalí XNU jádro na fyzickou bázi `0x80000000`, předá Apple Device Tree (`willow.adt`) s parametry příkazové řádky (`boot-args`) a spustí `start.s`.
5. **Start jádra XNU**: Inicializuje virtuální paměť Kryo jader, namapuje framebuffer (`0x5c000000`), inicializuje SDHCI řadič eMMC úložiště a připojí root filesystem z oddílu `userdata`.
6. **Start uživatelského prostoru**: Jádro spustí `/sbin/launchd` (PID 1). Pomocí `libignition` a dynamických knihoven se nastartují systémové služby a grafické rozhraní.

---

## 4. Klíčové technické subsystémy

### 4.1. Grafika a hardwarová akcelerace Adreno 610
* **Původní stav**: Výchozí CoreAnimation v iOS nemá nativní backend pro čipy Qualcomm Adreno. Softwarový CPU rendering (softpipe) byl extrémně pomalý (cca 1–2 FPS).
* **Řešení**:
  * Kompilace **Mesa 25.0.7** s Gallium driverem **freedreno** přímo pro iOS arm64.
  * Injektáž dynamických knihoven přes `topaz_inject`:
    * `libOSMesa.8.dylib` (Mesa jádro + freedreno driver komunikující s GPU Adreno 610).
    * `libtopaz-gl.dylib` (EAGLContext shim překládající volání CoreAnimation na OpenGL ES).
    * `libtopaz-inject.dylib` (zahákování virtuálních tabulek `CA::OGL::GLESContext`).
* **Výsledek**: Plná hardwarová akcelerace na 60 Hz (`sweetfb_hz=60`). GUI je naprosto plynulé, animace Lock Screenu běží v reálném čase.

### 4.2. Úložiště eMMC a souborový systém
* `willow` používá eMMC 5.1 řízené Qualcomm SDHCI v5 kontrolérem (`0x04744000`).
* V `sweet_ufs.c` je implementován plnohodnotný polling blokový ovladač obsluhující příkazy `CMD17`/`CMD18` (čtení) a `CMD24`/`CMD25` (zápis).
* Ovladač čte tabulku oddílů GPT:
  * Oddíl `userdata` (LBA `12582912`) slouží jako čtecí i zapisovatelný kořenový disk `/dev/disk0`.
  * Oddíl `boot` slouží pro ukládání diagnostických kruhových logů jádra (`sweet-log`).

### 4.3. Dotykový panel (Novatek NT36672A SPI)
* Dotykový digitizer je k procesoru připojen přes rozhraní **QUP0 SE2 SPI** (`0x04a88000`):
  * **GPIO 87**: Hardware Reset (aktivní v LOW).
  * **GPIO 88**: Interrupt / IRQ pin (čtení stavu přerušení).
  * **GPIO 9**: Chip Select (manuální GPIO CS, v protokolu tohoto panelu je **Active High** – klid 0, přenos 1).
  * **GPIO 6, 7, 8**: SPI MOSI, MISO, CLK (namuxovány na funkci `qup02`).
* **Kritická oprava v `gui35`**:
  * Čipset SM6125 (Trinket) má jednotnou bázi TLMM na adrese `0x00400000` (na rozdíl od starších čipsetů jako SM7150/SM7325, které měly WEST tile na `0x00500000`).
  * Oprava báze z `0x500000` na `0x400000` zajistila, že signály resetu, CS a dat fyzicky dosáhnou řadiče dotyku.
  * Implementována 4kroková bootloader inicializační sekvence zjištěná reverzním inženýrstvím stock kernelu:
    1. Zápis `0x5a` na adresu `0x7fff80` (delay 10 ms).
    2. Zápis `0x69` na adresu `0x3f0fe` (delay 35 ms).
    3. Zápis `0x00` na adresu `0x3f310` (delay 5 ms).
    4. Obnova stránky na 0 (`{0xff, 0x00, 0x00}`).

### 4.4. Uživatelské prostředí a obcházení aktivace (SpringBoard)
* V `libtopaz-inject.dylib` jsou implementovány zásahy pro bezproblémový běh iOS bez proprietárního Apple hardwaru:
  * `mobileactivationd`: Hooky `should_hactivate -> 1` a emulace `DataArk` (obejití nutnosti připojení k Apple aktivačním serverům).
  * `SBSetupManager`: Hook `_setSetupRequiredReason: -> 0` (přeskočení úvodního průvodce nastavením, který vyžaduje SEP).
  * Neutralizace zbytných služeb způsobujících zacyklení a přehřívání: `ReportCrash`, `bluetoothd`, `homed`, `assetsd`, `nanotimekitcompaniond`, `CollectionsPoster`.
  * **Programatický Auto-Unlock (`sb_unlock_worker`)**: Asynchronní vlákno, které vyčká na vytvoření instance `UIApplication`, nechá vykreslit Lock Screen a následně odešle interní zprávu `[SBLockScreenManager sharedInstance] unlockUIFromSource:17 withOptions:nil` pro automatické odemknutí na plochu (Home Screen).

---

## 5. Přehled patchů jádra pro willow (`0951`–`0955`)

Všechny patche jsou uloženy v adresáři `xnu/patches/`:

1. **`0951-willow-board-ram-display-1080x2340.patch`**:
   * Mapování framebufferu na `0x5c000000` pro 16K i 4K stránkování.
   * Přizpůsobení geometrie displeje na 1080 × 2340 bodů (stride 4320 BGRX8888).
   * Přemístění nouzového GPU fondu do volné nízké paměti RAM (`0x64000000..0x7c000000`).
2. **`0952-willow-sdhci-emmc-root-storage.patch`**:
   * Ovladač Qualcomm SDHCI MSM v5 pro čtení/zápis na interní eMMC.
   * GPT skener a napojení oddílu `userdata` na VFS jako rootfs.
3. **`0953-willow-touch-nt36672a-spi-ft8719.patch`**:
   * Implementace SPI masteru QUP0 SE2 a obsluha protokolu Novatek NT36672A.
   * Správné namapování TLMM báze `0x00400000` pro ovládání GPIO pinů dotyku na SM6125.
4. **`0954-willow-pmi632-battery-charger.patch`**:
   * Úprava SPMI sběrnice pro čtení palivoměru PMI632 QG a nabíječky SMB5 na USID 2.
5. **`0955-willow-usb-dwc3-qusb2-smmu.patch`**:
   * Podpora USB řadiče DWC3 a QUSB2 PHY pro síťové ladění přes USB Ethernet.

---

## 6. Aktuální stav projektu (Milník `gui35` – listopad 2026)

### Co je plně funkční a ověřené:
* [x] **Zavaděč a Shim**: Spolehlivé spouštění přes `fastboot boot` bez poškození oddílů Androidu.
* [x] **Jádro XNU**: Plný start všech 8 jader procesoru, správa paměti, VFS a blokové vrstvy.
* [x] **Displej**: Stabilní obraz v plném rozlišení 1080 × 2340, korektní barvy, žádné artefakty.
* [x] **Hardwarová akcelerace GPU**: Mesa Freedreno Adreno 610 běží na plných 60 FPS, rozhraní je zcela plynulé.
* [x] **Systémové služby iOS 16**: `launchd`, `backboardd`, `SpringBoard` a `mobileactivationd` běží stabilně.
* [x] **Uživatelské rozhraní**: Zobrazen plnohodnotný nativní Lock Screen iOS 16 (hodiny, datum, tapeta).
* [x] **Stabilita SpringBoardu**: Vyřešen pád `NSInternalInconsistencyException` díky bezpečné synchronizaci s `UIApplication`.
* [x] **Hardwarové adresování dotyku**: TLMM báze v jádře opravena na `0x00400000` (signály pro reset a SPI CS fyzicky dosahují řadiče).

### Na čem se aktuálně pracuje / otevřené úkoly:
1. **Ověření odezvy dotyku v `gui35`**:
   * Zkontrolovat, zda dotykový řadič Novatek NT36672A začal odesílat souřadnice a zda obrazovka reaguje na fyzické gesto tažení prstem (swipe-up).
2. **Přechod z Lock Screenu na Home Screen**:
   * Zajištění úspěšného automatického odemknutí přes `unlockUIFromSource:17` po startu, aby se zobrazila plocha s ikonami aplikací.
3. **Další periferie (následné fáze)**:
   * Zvukový výstup (WCD9370 / PMIC audio kodek).
   * Bezdrátové sítě (Wi-Fi WCN3990 a Bluetooth).
   * Indikace stavu baterie v horním stavovém řádku.

---

## 7. Důležité soubory a cesty v repozitáři

| Cesta k souboru | Popis a význam |
|---|---|
| `NOTES.md` | Podrobný technický deník všech milníků, reverzního inženýrství a analýz pádů |
| `xnu/patches/0951..0955` | Sada patchů jádra XNU pro Xiaomi Redmi Note 8T (`willow`) |
| `xnu/out/kernel.development.sweet` | Zkompilovaný binární obraz jádra XNU |
| `xnu/out/willow.adt` | Binární strom Apple Device Tree obsahující systémové bloby |
| `userland/gpu/topaz_inject.c` | Zdrojový kód injektované dylib pro hooks, Auto-Unlock a aktivaci |
| `scratch/gpu/libtopaz-inject.dylib` | Zkompilovaná knihovna `topaz-inject` generovaná GitHub Actions CI |
| `scratch/gpu/libtopaz-gl.dylib` | OpenGL ES shim pro CoreAnimation |
| `scratch/gpu/libOSMesa.8.dylib` | Ovladač Mesa Gallium Freedreno (Adreno 610) |
| `tools/mkpayload.py` | Nástroj pro vytvoření spojeného payloadu (jádro + ADT) |
| `tools/pack_evox_boot.py` | Nástroj pro zabalení výsledného boot obrazu pro fastboot |
| `shim/out/shim-evox-boot-gui35.img` | Aktuální spustitelný boot image sestavení `gui35` |

---

## 8. Postup sestavení a spuštění nového buildu

1. **Úprava zdrojů a kompilace dylib**:
   * Úpravy v `userland/gpu/topaz_inject.c` se pushnou do `origin/main`.
   * GitHub Actions workflow `gpu.yml` zkompiluje dylibs na macOS runneru za ~2,5 minuty.
   * Nové knihovny se stáhnou pomocí: `gh release download gpu-latest --dir scratch/gpu-ci --clobber`.
2. **Zabalení systémových blobů a ADT**:
   ```powershell
   python tools/mkblobs.py scratch/blobs.bin scratch/gpu/libOSMesa.8.dylib scratch/gpu/libtopaz-inject.dylib scratch/gpu/libtopaz-gl.dylib
   python tools/mkadt.py xnu/out/willow.adt --blobs scratch/blobs.bin
   ```
3. **Sestavení Payloadu**:
   ```powershell
   python tools/mkpayload.py -k xnu/out/kernel.development.sweet -d xnu/out/willow.adt -o xnu/out/payload-guiXX.bin --cmdline "debug=0xc serial=3 cpus=4 keepsyms=1 rd=ufsroot0 unentitled_ios_sim_launch=1 ignition_level=1 launchd_unsecure_cache=1 wdt_test=no_user_checkin wdt=-1 ufsrw=1 rootrw=1 sweetfb_hz=60 sweettouch=1 sweettouchdelay=3 gpu=1 gpu_mhz=600 launchd_disable_all_timeouts=1 sweetfb_noconsole=1 sweetfb_stayon=1 sweethidtest=3 topaz_inject=/private/var/tmp/libtopaz-inject.dylib,backboardd,containermanagerd,mobileactivationd,SpringBoard,CollectionsPoster,homed,assetsd,bluetoothd,ReportCrash,nanotimekitcompaniond,spindump gl=force"
   ```
4. **Zabalení Android Boot Image**:
   ```powershell
   python tools/pack_evox_boot.py shim/out/Image shim/out/shim-evox-boot-guiXX.img --payload xnu/out/payload-guiXX.bin
   ```
5. **Spuštění na telefonu**:
   * Přepnutí do bootloaderu: `platform-tools/adb.exe reboot bootloader`
   * Nabootování obrazu: `platform-tools/fastboot.exe boot shim/out/shim-evox-boot-guiXX.img`
