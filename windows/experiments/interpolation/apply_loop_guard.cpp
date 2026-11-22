#include "SpirvLoopFuel.h"
#include <cstdio>
#include <fcntl.h>
#include <io.h>

int main() {
    _setmode(_fileno(stdin), _O_BINARY);
    _setmode(_fileno(stdout), _O_BINARY);
    uint32_t n = 0;
    while (std::fread(&n, sizeof(n), 1, stdin) == 1) {
        if (n < 5 || n > (1u << 24)) return 2;
        std::vector<uint32_t> module(n);
        if (std::fread(module.data(), sizeof(uint32_t), n, stdin) != n) return 3;
        Libs::Graphics::SpirvLoopFuel::Apply(module);
        n = static_cast<uint32_t>(module.size());
        if (std::fwrite(&n, sizeof(n), 1, stdout) != 1 || std::fwrite(module.data(), sizeof(uint32_t), n, stdout) != n) return 4;
    }
    return std::ferror(stdin) || std::fflush(stdout) != 0;
}
