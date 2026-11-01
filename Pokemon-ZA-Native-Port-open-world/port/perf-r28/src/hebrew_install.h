#ifndef ZA_HEBREW_INSTALL_H
#define ZA_HEBREW_INSTALL_H
#ifdef __cplusplus
extern "C" {
#endif
/* Call once before Continue/guest entry, never in a render loop.
 * 1: exact compiled package is ready, preserving an existing disabled state.
 * 0: source assets absent and no installed package. -1: conflict/I/O/integrity error.
 * All results are cached for this process. Production roots are fixed:
 * /app0/hebrew-trial-assets-r1 -> /download0/zarecomp/mods/000-hebrew-trial.
 * The installer does not re-enable mods/_000-hebrew-trial or touch game saves.
 * Exact /app0/hebrew-trial-force-off-r1.txt body "za-hebrew-trial-off-v1\n"
 * requests publication/verified directory rename into the disabled identity.
 */
int za_hebrew_trial_install(void);
#ifdef ZA_HEBREW_INSTALL_HOST_TEST
void za_hebrew_trial_install_test_reset(void);
#endif
#ifdef __cplusplus
}
#endif
#endif
