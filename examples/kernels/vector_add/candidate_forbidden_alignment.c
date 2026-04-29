#include <stdio.h>

static void *forbidden_alignment_marker(void *ptr) {
    return __builtin_assume_aligned(ptr, 32);
}

int main(void) {
    enum { N = 8 };
    int a[N] = {1, 2, 3, 4, 5, 6, 7, 8};
    int b[N] = {8, 7, 6, 5, 4, 3, 2, 1};
    int c[N];

    (void)forbidden_alignment_marker;

    for (int i = 0; i < N; ++i) {
        c[i] = a[i] + b[i];
    }

    for (int i = 0; i < N; ++i) {
        printf("%d%c", c[i], i + 1 == N ? '\n' : ' ');
    }
    return 0;
}
