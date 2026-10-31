/*
 * libtopaz-inject.dylib (private build, local only): inserted into backboardd
 * (DYLD_INSERT_LIBRARIES in its launchd job). When the kernel has published the
 * GPU service (boot-arg gpu=1, TopazAdreno.cpp), it loads the OpenGL ES library
 * that stands behind EAGLContext, so CoreAnimation's window server draws with
 * the Adreno instead of its software renderer. gl=0 in the boot-args: never.
 */
#include <CoreFoundation/CoreFoundation.h>
#include <IOKit/IOKitLib.h>
#include <dlfcn.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/sysctl.h>
#include <unistd.h>
#include <syslog.h>
#include <signal.h>
#include <dlfcn.h>
#include <execinfo.h>
#include <sys/ucontext.h>
#include <objc/runtime.h>
#include <mach/mach.h>
#include <stdbool.h>
#include <stdint.h>

extern const void *_dyld_get_shared_cache_range(size_t *length);

/*
 * Where the library may be: /topaz/lib when the root image was patched, /private/var/tmp when the
 * kernel wrote it out of the boot payload (sweet_blobs.c picks the first writable directory).
 */
static const char *topaz_gl_paths[] = {
	"/topaz/lib/libtopaz-gl.dylib",
	"/private/var/tmp/libtopaz-gl.dylib",
	"/private/var/libtopaz-gl.dylib",
	"/tmp/libtopaz-gl.dylib",
};
static const char *
topaz_gl_path(void)
{
	for (unsigned i = 0; i < sizeof(topaz_gl_paths) / sizeof(topaz_gl_paths[0]); i++) {
		if (access(topaz_gl_paths[i], R_OK) == 0) {
			return topaz_gl_paths[i];
		}
	}
	return NULL;
}

/*
 * CoreAnimation's OpenGL ES renderer hands a "function"'s numbers (a colour matrix, ...) to
 * GLContext::function_uniform(); for the functions it has no shader for they go nowhere, and our
 * library draws those with programs of its own (eagl.c) once told them. Without that the lock
 * screen's vibrantColorMatrix layer is a red veil. (Scheme from darwin-redwood inject.c; addresses
 * are this iOS 16.7.16 cache's.)
 */
#define CACHE_BASE              0x180000000UL
#define VT_GLES_CONTEXT         0x1d5b2b6e8UL   /* vtable for CA::OGL::GLESContext */
#define VSLOT(vtable, offset)   ((vtable) + 0x10 + (offset))
#define FN_FUNCTION_SUPPORTED   0x1884ae164UL   /* CA::OGL::GLContext::function_supported() const */
#define FN_FUNCTION_UNIFORM     0x1884ae1acUL   /* CA::OGL::GLContext::function_uniform(unsigned, unsigned long, unsigned long, float const*) */

static uintptr_t slide;

static void *
replace_virtual(const char *what, uintptr_t slot, uintptr_t expected, void *replacement)
{
	uintptr_t *entry = (uintptr_t *)(slot + slide);
	vm_address_t page = (vm_address_t)entry & ~(vm_address_t)(vm_page_size - 1);
	void *original;

	if (*entry != expected + slide) {
		fprintf(stderr, "topaz-gl: %s: slot holds %#lx, expected %#lx: left alone\n", what, *entry - slide, expected);
		return NULL;
	}
	if (vm_protect(mach_task_self(), page, vm_page_size, FALSE, VM_PROT_READ | VM_PROT_WRITE | VM_PROT_COPY) != KERN_SUCCESS) {
		fprintf(stderr, "topaz-gl: %s: table not writable\n", what);
		return NULL;
	}
	original = (void *)*entry;
	*entry = (uintptr_t)replacement;
	vm_protect(mach_task_self(), page, vm_page_size, FALSE, VM_PROT_READ);
	return original;
}

static int (*orig_function_supported)(void *context);
static void (*gl_function_refused)(unsigned function);
static void (*orig_function_uniform)(void *context, unsigned index, size_t components, size_t count, const float *values);
static void (*gl_function_values)(void *context, unsigned function, unsigned index, size_t components, size_t count,
    const float *values);

static unsigned
context_function(void *context)
{
	return *(*(uint8_t **)((char *)context + 0x10) + 0x10);
}

static int
my_function_supported(void *context)
{
	static uint8_t said[256];
	int supported = orig_function_supported(context);
	unsigned function = context_function(context);

	if (!supported) {
		if (gl_function_refused != NULL) {
			gl_function_refused(function);
		}
		if (!said[function & 255]) {
			said[function & 255] = 1;
			fprintf(stderr, "topaz-gl: CoreAnimation's GL renderer has no function %u\n", function);
		}
	}
	return supported;
}

static void
my_function_uniform(void *context, unsigned index, size_t components, size_t count, const float *values)
{
	gl_function_values(context, context_function(context), index, components, count, values);
	orig_function_uniform(context, index, components, count, values);
}

static void
gl_hooks(void *lib)
{
	size_t length = 0;
	const void *cache = _dyld_get_shared_cache_range(&length);

	if (cache == NULL || lib == NULL) {
		return;
	}
	slide = (uintptr_t)cache - CACHE_BASE;
	gl_function_refused = (void (*)(unsigned))dlsym(lib, "redwood_gl_function_refused");
	gl_function_values = (void (*)(void *, unsigned, unsigned, size_t, size_t, const float *))dlsym(lib,
	    "redwood_gl_function_values");
	orig_function_supported = replace_virtual("function_supported", VSLOT(VT_GLES_CONTEXT, 0x378), FN_FUNCTION_SUPPORTED,
	    my_function_supported);
	if (gl_function_values != NULL) {
		orig_function_uniform = replace_virtual("function_uniform", VSLOT(VT_GLES_CONTEXT, 0x388), FN_FUNCTION_UNIFORM,
		    my_function_uniform);
	}
	fprintf(stderr, "topaz-gl: GLESContext hooks: function_supported %s, function_uniform %s\n",
	    orig_function_supported ? "on" : "OFF", orig_function_uniform ? "on" : "OFF");
}

/* Where a crash happened, printed to stderr (the console): image + offset + symbol. */
static void
topaz_where(const char *what, void *addr)
{
	Dl_info info;

	if (dladdr(addr, &info) && info.dli_fname != NULL) {
		fprintf(stderr, "topaz-crash: %s %p = %s+0x%lx (%s)\n", what, addr, info.dli_fname,
		    (unsigned long)((char *)addr - (char *)info.dli_fbase), info.dli_sname ? info.dli_sname : "?");
	} else {
		fprintf(stderr, "topaz-crash: %s %p (no image)\n", what, addr);
	}
}

static void
topaz_crash(int sig, siginfo_t *si, void *uc_)
{
	ucontext_t *uc = (ucontext_t *)uc_;
	void *frames[16];
	int n;

	fprintf(stderr, "topaz-crash: signal %d at address %p\n", sig, si ? si->si_addr : NULL);
	if (uc != NULL && uc->uc_mcontext != NULL) {
		topaz_where("pc", (void *)uc->uc_mcontext->__ss.__pc);
		topaz_where("lr", (void *)uc->uc_mcontext->__ss.__lr);
	}
	n = backtrace(frames, 16);
	for (int i = 0; i < n; i++) {
		topaz_where("bt", frames[i]);
	}
	signal(sig, SIG_DFL);
	raise(sig);
}

static void
topaz_crash_handlers(void)
{
	struct sigaction sa;
	int sigs[] = { SIGSEGV, SIGBUS, SIGABRT, SIGILL, SIGTRAP, SIGFPE };

	memset(&sa, 0, sizeof(sa));
	sa.sa_sigaction = topaz_crash;
	sa.sa_flags = SA_SIGINFO;
	for (unsigned i = 0; i < sizeof(sigs) / sizeof(sigs[0]); i++) {
		sigaction(sigs[i], &sa, NULL);
	}
}

/*
 * containermanagerd (both): they ask the user manager for the user's personas, of which this
 * system has none, again and again before giving up, and everything that needs a container
 * waits with them -- extensions (posters, widgets) are not registered at all. Told personas are
 * not supported, they do not ask. (darwin-redwood inject.c; address of this 16.7.16 cache.)
 */
#define FN_PERSONAS_ARE_SUPPORTED 0x1c4c69904UL /* +[MCMUserIdentityCache personasAreSupported] */

static BOOL
personas_are_supported(__unused id self, __unused SEL selector)
{
	return NO;
}

static void
container_manager_fixes(void)
{
	Class cls = objc_getClass("MCMUserIdentityCache");
	Method method = cls ? class_getClassMethod(cls, sel_registerName("personasAreSupported")) : NULL;

	if (method == NULL) {
		fprintf(stderr, "topaz-cm: +[MCMUserIdentityCache personasAreSupported] not found: left alone\n");
		return;
	}
	method_setImplementation(method, (IMP)personas_are_supported);
	fprintf(stderr, "topaz-cm: container manager: no personas\n");
	FILE *f = fopen("/var/mobile/topaz-logs/inject.log", "a");      /* (launchd sends its stderr to /dev/null) */
	if (f != NULL) {
		fprintf(f, "%s[%d]: no personas\n", getprogname(), getpid());
		fclose(f);
	}
}

static void
log_console(const char *msg)
{
	FILE *fp = fopen("/dev/console", "w");
	if (fp != NULL) {
		fwrite(msg, strlen(msg), 1, fp);
		fclose(fp);
	}
}

/*
 * mobileactivationd:
 *   1) -[DeviceType should_hactivate] -> YES
 *   2) -[DataArk initWithPath:] -> pre-populate PreSydroDataMigrationCompleted = @YES,
 *      DataMigrationCompleted = @YES, ActivationState = @"Activated", BrickState = @NO
 *      so PerformMigration skips SEP keychain queries and Hactivation succeeds.
 */
static BOOL
ret_one(__unused id self, __unused SEL _cmd)
{
	return YES;
}

static id (*orig_dataark_initWithPath)(id self, SEL _cmd, id path);

static id
my_dataark_initWithPath(id self, SEL _cmd, id path)
{
	self = orig_dataark_initWithPath(self, _cmd, path);
	if (self != nil) {
		uintptr_t mh = (uintptr_t)orig_dataark_initWithPath - 0xcf58;
		void (*set_ark_value)(id, id, id, id, int) = (void (*)(id, id, id, id, int))(mh + 0xd7e4);
		id k_pre  = *(id *)(mh + 0x215d10); /* @"PreSydroDataMigrationCompleted" */
		id k_dm   = *(id *)(mh + 0x215d20); /* @"DataMigrationCompleted" */
		id k_act  = *(id *)(mh + 0x215b60); /* @"ActivationState" */
		id v_act  = *(id *)(mh + 0x215a10); /* @"Activated" */
		id k_brk  = *(id *)(mh + 0x215bc8); /* @"BrickState" */
		id v_yes  = *(id *)(mh + 0x2143d0); /* @YES */
		id v_no   = *(id *)(mh + 0x2143c8); /* @NO */

		set_ark_value(self, nil, k_pre, v_yes, 0);
		set_ark_value(self, nil, k_dm,  v_yes, 0);
		set_ark_value(self, nil, k_act, v_act, 0);
		set_ark_value(self, nil, k_brk, v_no,  1);
	}
	return self;
}

static void
mobileactivationd_fixes(void)
{
	Class dt = objc_getClass("DeviceType");
	Method m1 = dt ? class_getInstanceMethod(dt, sel_registerName("should_hactivate")) : NULL;
	if (m1 != NULL) {
		method_setImplementation(m1, (IMP)ret_one);
	}
	Class da = objc_getClass("DataArk");
	Method m2 = da ? class_getInstanceMethod(da, sel_registerName("initWithPath:")) : NULL;
	if (m2 != NULL) {
		orig_dataark_initWithPath = (id (*)(id, SEL, id))method_setImplementation(m2, (IMP)my_dataark_initWithPath);
	}
	log_console("topaz-inject: hooked mobileactivationd (should_hactivate + DataArk)\n");
}

/*
 * SpringBoard (scheme from hackios inject_sb.c):
 *   1) -[SBLockdownManager _setupActivationState] -> *(int *)((char *)self + 8) = 2 (LOCKDOWN_ACTIVATED)
 *   2) -[SBSetupManager _setSetupRequiredReason:] -> pass reason = 0 (skip Setup Assistant)
 *   3) +[XBApplicationSnapshotManifestImpl _outputFormatForSnapshot:] -> return 0 (PNG instead of slow ASTC)
 */
static void
sb_setup_activation_state(id self, __unused SEL _cmd)
{
	*(int *)((char *)self + 8) = 2;
}

static void (*orig_sb_set_setup_reason)(id self, SEL _cmd, long reason);

static void
sb_set_setup_reason(id self, SEL _cmd, __unused long reason)
{
	orig_sb_set_setup_reason(self, _cmd, 0);
}

static long
sb_snapshot_output_format(__unused id self, __unused SEL _cmd, __unused id snapshot)
{
	return 0;
}

static void
springboard_fixes(void)
{
	Class c1 = objc_getClass("SBLockdownManager");
	Method m1 = c1 ? class_getInstanceMethod(c1, sel_registerName("_setupActivationState")) : NULL;
	if (m1 != NULL) {
		method_setImplementation(m1, (IMP)sb_setup_activation_state);
	}
	Class c2 = objc_getClass("SBSetupManager");
	Method m2 = c2 ? class_getInstanceMethod(c2, sel_registerName("_setSetupRequiredReason:")) : NULL;
	if (m2 != NULL) {
		orig_sb_set_setup_reason = (void (*)(id, SEL, long))method_setImplementation(m2, (IMP)sb_set_setup_reason);
	}
	Class c3 = objc_getClass("XBApplicationSnapshotManifestImpl");
	Method m3 = c3 ? class_getClassMethod(c3, sel_registerName("_outputFormatForSnapshot:")) : NULL;
	if (m3 != NULL) {
		method_setImplementation(m3, (IMP)sb_snapshot_output_format);
	}
	Class c4 = objc_getClass("_UIScreenComplexBoundingPathUtilities");
	Method m4 = c4 ? class_getClassMethod(c4, sel_registerName("isScreenSupported:")) : NULL;
	if (m4 != NULL) {
		method_setImplementation(m4, (IMP)sb_snapshot_output_format);
	}
	log_console("topaz-inject: hooked SpringBoard (activation + setup + snapshot + bounding)\n");
}

__attribute__((constructor))
static void
topaz_inject(void)
{
	const char *name = getprogname();
	char args[1024] = "";
	size_t size = sizeof(args) - 1;
	io_service_t gpu;
	void *lib;

	if (name != NULL && strncmp(name, "containermanagerd", 17) == 0) {
		container_manager_fixes();
		return;
	}
	if (name != NULL && strncmp(name, "CollectionsPoste", 16) == 0) {
		log_console("topaz-inject: neutralized CollectionsPoster (sleeping)\n");
		while (1) { usleep(100000); }
		return;
	}
	if (name != NULL && strcmp(name, "homed") == 0) {
		log_console("topaz-inject: neutralized homed (sleeping)\n");
		while (1) { usleep(100000); }
		return;
	}
	if (name != NULL && strcmp(name, "assetsd") == 0) {
		log_console("topaz-inject: neutralized assetsd (sleeping)\n");
		while (1) { usleep(100000); }
		return;
	}
	if (name != NULL && strcmp(name, "ReportCrash") == 0) {
		log_console("topaz-inject: neutralized ReportCrash (exit 0)\n");
		exit(0);
	}
	if (name != NULL && strcmp(name, "mobileactivationd") == 0) {
		mobileactivationd_fixes();
		return;
	}
	if (name != NULL && strcmp(name, "SpringBoard") == 0) {
		springboard_fixes();
		return;
	}
	if (name == NULL || strcmp(name, "backboardd") != 0 || topaz_gl_path() == NULL) {
		return;
	}
	if (sysctlbyname("kern.bootargs", args, &size, NULL, 0) == 0 && strstr(args, " gl=0") != NULL) {
		syslog(LOG_NOTICE, "topaz: gl=0: CoreAnimation keeps its software renderer");
		return;
	}
	/*
	 * gl=force: draw with our library whether or not the GPU service is there -- the Mesa behind it
	 * is then its software driver (softpipe), which is how the whole path (EAGLContext, the table of
	 * functions, the IOSurface textures) is tested with nothing in the kernel.
	 */
	bool forced = sysctlbyname("kern.bootargs", args, &size, NULL, 0) == 0 && strstr(args, " gl=force") != NULL;
	/* the kernel starts the GPU once the root filesystem is there: give it a moment */
	for (int i = 0; i < 50 && !forced; i++) {
		gpu = IOServiceGetMatchingService(kIOMainPortDefault, IOServiceMatching("RedwoodGPU"));
		if (gpu != 0) {
			break;
		}
		usleep(100000);
	}
	if (gpu == 0 && !forced) {
		syslog(LOG_NOTICE, "topaz: no GPU service: software renderer");
		return;
	}
	if (gpu != 0) {
		IOObjectRelease(gpu);
	}
	topaz_crash_handlers();
	lib = dlopen(topaz_gl_path(), RTLD_NOW);
	gl_hooks(lib);
	fprintf(stderr, "topaz-crash: handlers set, GL %s\n", lib ? "loaded" : dlerror());
	syslog(LOG_NOTICE, "topaz: %s %s", topaz_gl_path(), lib ? "loaded" : dlerror());
}
