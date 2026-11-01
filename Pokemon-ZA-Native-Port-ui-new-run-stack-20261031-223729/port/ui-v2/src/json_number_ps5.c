/* The PS5 libc advertises an empty decimal point and strtod stops at '.'.
 * nlohmann's lexer therefore inserts NUL into a fractional token and aborts.
 * Link this once with --wrap=localeconv and --wrap=strtod: every frozen JSON
 * instantiation uses the same C ABI fix, without changing vendor headers or
 * the process locale. The number conversion is the runtime's existing parser.
 */
#include <limits.h>
#include <locale.h>

extern double plat_strtod(const char *text, char **end);

static char decimal_point[] = ".";
static char empty[] = "";
static struct lconv c_locale = {
    .decimal_point = decimal_point,
    .thousands_sep = empty,
    .grouping = empty,
    .int_curr_symbol = empty,
    .currency_symbol = empty,
    .mon_decimal_point = empty,
    .mon_thousands_sep = empty,
    .mon_grouping = empty,
    .positive_sign = empty,
    .negative_sign = empty,
    .int_frac_digits = CHAR_MAX,
    .frac_digits = CHAR_MAX,
    .p_cs_precedes = CHAR_MAX,
    .p_sep_by_space = CHAR_MAX,
    .n_cs_precedes = CHAR_MAX,
    .n_sep_by_space = CHAR_MAX,
    .p_sign_posn = CHAR_MAX,
    .n_sign_posn = CHAR_MAX,
    .int_p_cs_precedes = CHAR_MAX,
    .int_p_sep_by_space = CHAR_MAX,
    .int_n_cs_precedes = CHAR_MAX,
    .int_n_sep_by_space = CHAR_MAX,
    .int_p_sign_posn = CHAR_MAX,
    .int_n_sign_posn = CHAR_MAX,
};

struct lconv *__wrap_localeconv(void) { return &c_locale; }

double __wrap_strtod(const char *text, char **end) {
    return plat_strtod(text, end);
}
