#include <windows.h>
#include <shlwapi.h>
#include <cstdio>
#include <string>

int wmain() {
    wchar_t filename[32768];
    const DWORD size = GetModuleFileNameW(nullptr, filename, ARRAYSIZE(filename));
    if (!size || size >= ARRAYSIZE(filename)) return 1;
    const std::wstring image(filename, size);
    const std::wstring folder = image.substr(0, image.find_last_of(L'\\'));
    const std::wstring python = folder + L"\\tools\\python\\python.exe";
    const wchar_t* tail = PathGetArgsW(GetCommandLineW());
    std::wstring command = L"\"" + python + L"\" -I -B -u \"" + folder +
                           L"\\windows\\drop_in\\play.py\" " + tail;
    STARTUPINFOW startup{};
    startup.cb = sizeof(startup);
    PROCESS_INFORMATION process{};
    if (!CreateProcessW(python.c_str(), command.data(), nullptr, nullptr, TRUE, 0,
                        nullptr, folder.c_str(), &startup, &process)) {
        MessageBoxW(nullptr, L"Extract the entire Saros Windows ZIP, then open Play Saros again.",
                    L"Saros — launcher files missing", MB_OK | MB_ICONERROR);
        return 1;
    }
    CloseHandle(process.hThread);
    WaitForSingleObject(process.hProcess, INFINITE);
    DWORD result = 1;
    GetExitCodeProcess(process.hProcess, &result);
    CloseHandle(process.hProcess);
    return static_cast<int>(result);
}
