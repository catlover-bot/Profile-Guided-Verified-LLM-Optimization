#include <stdio.h>

int main(void) {
    enum { N = 5 };
    int a[N] = {1, 2, 3, 4, 5};
    int b[N] = {5, 4, 3, 2, 1};
    int sum = 0;

    for (int i = 0; i < N; ++i) {
        sum += a[i] * b[i];
    }

    printf("%d\n", sum);
    return 0;
}
