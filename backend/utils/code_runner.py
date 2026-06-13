"""安全沙箱：执行用户提交的编程题代码并对比测试用例输出。支持 Python、C++、Java、JavaScript、C。"""
import subprocess
import sys
import textwrap
import tempfile
import os


def run_code_against_tests(user_code: str, test_cases: list[dict], code_lang: str = "python") -> dict:
    """
    执行用户代码并逐一对比 test_cases。
    test_cases 格式: [{"input": "args_str", "expected": "str(result)"}]
    返回: {"passed": int, "total": int, "results": [...], "score": float}
    """
    lang = (code_lang or "python").lower().strip()
    runner = _LANG_RUNNERS.get(lang, _run_python_tests)
    return runner(user_code, test_cases)


def _run_python_tests(user_code: str, test_cases: list[dict]) -> dict:
    results = []
    passed = 0
    for tc in test_cases:
        input_str = tc.get("input", "")
        expected = str(tc.get("expected", "")).strip()
        script = textwrap.dedent(f"""
{user_code}

_result = {_extract_call(user_code, input_str)}
print(repr(_result))
""")
        try:
            proc = subprocess.run(
                [sys.executable, "-c", script],
                capture_output=True, text=True, timeout=5,
            )
            actual_clean = proc.stdout.strip()
            ok = _compare_result(actual_clean, expected)
            if not ok:
                ok = actual_clean.strip().strip("'\"") == expected.strip()
            if ok:
                passed += 1
            results.append({"input": input_str, "expected": expected, "actual": actual_clean, "passed": ok, "error": proc.stderr[:200] if proc.stderr else ""})
        except subprocess.TimeoutExpired:
            results.append({"input": input_str, "expected": expected, "actual": "", "passed": False, "error": "执行超时"})
        except Exception as e:
            results.append({"input": input_str, "expected": expected, "actual": "", "passed": False, "error": str(e)[:200]})
    return _build_result(results, passed)


def _run_cpp_tests(user_code: str, test_cases: list[dict]) -> dict:
    return _run_compiled_tests(user_code, test_cases, "cpp", "g++", _wrap_cpp_code)


def _run_c_tests(user_code: str, test_cases: list[dict]) -> dict:
    return _run_compiled_tests(user_code, test_cases, "c", "gcc", _wrap_c_code)


def _run_java_tests(user_code: str, test_cases: list[dict]) -> dict:
    results = []
    passed = 0
    try:
        with tempfile.TemporaryDirectory() as tmpdir:
            src_file = os.path.join(tmpdir, "Main.java")
            src_code = _wrap_java_code(user_code)
            with open(src_file, "w", encoding="utf-8") as f:
                f.write(src_code)
            compile_proc = subprocess.run(
                ["javac", src_file],
                capture_output=True, text=True, timeout=15,
            )
            if compile_proc.returncode != 0:
                err_msg = compile_proc.stderr[:200] or "编译失败"
                for tc in test_cases:
                    results.append({"input": tc.get("input", ""), "expected": str(tc.get("expected", "")), "actual": "", "passed": False, "error": err_msg})
                return _build_result(results, passed)

            for tc in test_cases:
                input_str = tc.get("input", "")
                expected = str(tc.get("expected", "")).strip()
                try:
                    proc = subprocess.run(
                        ["java", "-cp", tmpdir, "Main"] + _tokenize_args(input_str),
                        capture_output=True, text=True, timeout=5,
                    )
                    actual_clean = proc.stdout.strip()
                    ok = _compare_result(actual_clean, expected) or actual_clean.strip() == expected.strip()
                    if ok:
                        passed += 1
                    results.append({"input": input_str, "expected": expected, "actual": actual_clean, "passed": ok, "error": proc.stderr[:200] if proc.stderr else ""})
                except subprocess.TimeoutExpired:
                    results.append({"input": input_str, "expected": expected, "actual": "", "passed": False, "error": "执行超时"})
    except Exception as e:
        err = str(e)[:200]
        for tc in test_cases:
            results.append({"input": tc.get("input", ""), "expected": str(tc.get("expected", "")), "actual": "", "passed": False, "error": err})
        return _build_result(results, passed)
    return _build_result(results, passed)


def _run_js_tests(user_code: str, test_cases: list[dict]) -> dict:
    results = []
    passed = 0
    for tc in test_cases:
        input_str = tc.get("input", "")
        expected = str(tc.get("expected", "")).strip()
        fn_name = _extract_fn_name(user_code)
        args_str = input_str
        script = f"{user_code}\nconsole.log(JSON.stringify({fn_name}({args_str})));"
        try:
            proc = subprocess.run(
                ["node", "-e", script],
                capture_output=True, text=True, timeout=5,
            )
            actual_clean = proc.stdout.strip()
            ok = _compare_result(actual_clean, expected) or actual_clean.strip() == expected.strip()
            if ok:
                passed += 1
            results.append({"input": input_str, "expected": expected, "actual": actual_clean, "passed": ok, "error": proc.stderr[:200] if proc.stderr else ""})
        except subprocess.TimeoutExpired:
            results.append({"input": input_str, "expected": expected, "actual": "", "passed": False, "error": "执行超时"})
        except Exception as e:
            results.append({"input": input_str, "expected": expected, "actual": "", "passed": False, "error": str(e)[:200]})
    return _build_result(results, passed)


def _run_compiled_tests(user_code: str, test_cases: list[dict], ext: str, compiler: str, wrapper_fn) -> dict:
    results = []
    passed = 0
    try:
        with tempfile.TemporaryDirectory() as tmpdir:
            src_file = os.path.join(tmpdir, f"main.{ext}")
            src_code = wrapper_fn(user_code)
            with open(src_file, "w", encoding="utf-8") as f:
                f.write(src_code)
            exe_file = os.path.join(tmpdir, "main.exe" if sys.platform == "win32" else "main.out")
            compile_proc = subprocess.run(
                [compiler, src_file, "-o", exe_file],
                capture_output=True, text=True, timeout=15,
            )
            if compile_proc.returncode != 0:
                err_msg = compile_proc.stderr[:200] or "编译失败"
                for tc in test_cases:
                    results.append({"input": tc.get("input", ""), "expected": str(tc.get("expected", "")), "actual": "", "passed": False, "error": err_msg})
                return _build_result(results, passed)

            for tc in test_cases:
                input_str = tc.get("input", "")
                expected = str(tc.get("expected", "")).strip()
                try:
                    proc = subprocess.run(
                        [exe_file] + _tokenize_args(input_str),
                        capture_output=True, text=True, timeout=5,
                    )
                    actual_clean = proc.stdout.strip()
                    ok = _compare_result(actual_clean, expected) or actual_clean.strip() == expected.strip()
                    if ok:
                        passed += 1
                    results.append({"input": input_str, "expected": expected, "actual": actual_clean, "passed": ok, "error": proc.stderr[:200] if proc.stderr else ""})
                except subprocess.TimeoutExpired:
                    results.append({"input": input_str, "expected": expected, "actual": "", "passed": False, "error": "执行超时"})
    except FileNotFoundError:
        err_msg = f"编译器 {compiler} 未安装或不在PATH中"
        for tc in test_cases:
            results.append({"input": tc.get("input", ""), "expected": str(tc.get("expected", "")), "actual": "", "passed": False, "error": err_msg})
        return _build_result(results, passed)
    except Exception as e:
        err = str(e)[:200]
        for tc in test_cases:
            results.append({"input": tc.get("input", ""), "expected": str(tc.get("expected", "")), "actual": "", "passed": False, "error": err})
        return _build_result(results, passed)
    return _build_result(results, passed)


def _wrap_cpp_code(user_code: str) -> str:
    fn_name = _extract_fn_name(user_code)
    lines = user_code.strip().split("\n")
    return """#include <iostream>
#include <vector>
#include <string>
#include <algorithm>
#include <sstream>
using namespace std;

""" + user_code + """

int main() {
    string line;
    getline(cin, line);
""" + _gen_cpp_main_body(fn_name, lines) + """
    return 0;
}
"""


def _wrap_c_code(user_code: str) -> str:
    fn_name = _extract_fn_name(user_code)
    return """#include <stdio.h>
#include <stdlib.h>
#include <string.h>

""" + user_code + """

int main() {
    char line[4096];
    if (fgets(line, sizeof(line), stdin)) {
        size_t len = strlen(line);
        if (len > 0 && line[len-1] == '\\n') line[len-1] = 0;
""" + _gen_c_main_body(fn_name) + """
    }
    return 0;
}
"""


def _wrap_java_code(user_code: str) -> str:
    fn_name = _extract_fn_name(user_code)
    lines = user_code.strip().split("\n")
    return """import java.util.*;

public class Main {
""" + _indent_java_body(user_code) + """

    public static void main(String[] args) {
        java.util.Scanner sc = new java.util.Scanner(System.in);
        String line = sc.nextLine();
""" + _gen_java_main_body(fn_name, lines) + """
    }
}
"""


def _indent_java_body(code: str) -> str:
    return "\n".join("    " + line for line in code.strip().split("\n"))


def _gen_cpp_main_body(fn_name: str, lines: list[str]) -> str:
    params = _extract_param_types(lines)
    call = _gen_cpp_call(fn_name, params)
    return f"""    auto result = {call};
    cout << result << endl;
"""


def _gen_c_main_body(fn_name: str) -> str:
    # C needs careful handling — for now, call the function and print int result
    return f"""        int result = {fn_name}(line);
        printf("%d\\n", result);
"""


def _gen_java_main_body(fn_name: str, lines: list[str]) -> str:
    call = _gen_java_call(fn_name, lines)
    output_call = f"System.out.println({call});"
    return f"        {output_call}\n"


def _gen_cpp_call(fn_name: str, params: list[str]) -> str:
    if not params:
        return f"{fn_name}(line)"
    arg_parts = []
    line_idx = [0]

    def next_token():
        return f"stoi(tokens[{line_idx[0]}])" if line_idx[0] < len(params) else f"tokens[{line_idx[0]}]"

    for pt in params:
        pt_lower = pt.lower()
        if "vector" in pt_lower or "array" in pt_lower or "list" in pt_lower:
            arg_parts.append(f"parseVector(tokens[{line_idx[0]}])")
        elif "string" in pt_lower:
            arg_parts.append(f"tokens[{line_idx[0]}]")
        elif "int" in pt_lower or "float" in pt_lower or "double" in pt_lower:
            arg_parts.append(next_token())
        else:
            arg_parts.append(f"tokens[{line_idx[0]}]")
        line_idx[0] += 1

    if len(params) > 1:
        body = f"""    istringstream iss(line);
    vector<string> tokens;
    string token;
    while (iss >> token) tokens.push_back(token);
    auto result = {fn_name}({', '.join(arg_parts)});
    cout << result << endl;
"""
        return f"""    istringstream iss(line);
    vector<string> tokens;
    string token;
    while (iss >> token) tokens.push_back(token);
    auto result = {fn_name}({', '.join(arg_parts)});
    cout << result << endl;
"""
    sorted_body = """    istringstream iss(line);
    vector<string> tokens;
    string token;
    while (iss >> token) tokens.push_back(token);
    auto result = """
    sorted_body += f"{fn_name}({', '.join(arg_parts)});\n    cout << result << endl;\n"
    return sorted_body


def _gen_java_call(fn_name: str, lines: list[str]) -> str:
    params = _extract_param_types(lines)
    if not params:
        return f"{fn_name}(line)"
    arg_parts = []
    for pt in params:
        pt_lower = pt.lower()
        if "list" in pt_lower or "array" in pt_lower or "vector" in pt_lower or "int[]" in pt_lower:
            arg_parts.append("parseIntArray(parts[i])")
        elif "string" in pt_lower:
            arg_parts.append("parts[i]")
        elif "int" in pt_lower:
            arg_parts.append("Integer.parseInt(parts[i])")
        elif "double" in pt_lower or "float" in pt_lower:
            arg_parts.append("Double.parseDouble(parts[i])")
        else:
            arg_parts.append("parts[i]")
    sorted_body = f"String[] parts = line.split(\",\\\\s*\");\n"
    sorted_body += "        " + f"System.out.println({fn_name}("
    for i, ap in enumerate(arg_parts):
        part_var = ap.replace("parts[i]", f"parts[{i}]")
        if i > 0:
            sorted_body += ", "
        sorted_body += part_var
    sorted_body += "));"
    return sorted_body


def _extract_fn_name(user_code: str) -> str:
    for line in user_code.splitlines():
        line = line.strip()
        if line.startswith("def "):
            return line[4:line.index("(")]
        if "(" in line and ("public" in line or "static" in line or "int " in line or "void " in line or "String " in line or "boolean " in line or "double " in line or "float " in line or "long " in line or "char " in line):
            tokens = line.replace("(", " (").split()
            for i, t in enumerate(tokens):
                if t.strip() == "(":
                    for j in range(i - 1, -1, -1):
                        if tokens[j] not in ("public", "static", "int", "void", "String", "boolean", "double", "float", "long", "char", "const", "auto"):
                            return tokens[j]
    return "main"


def _extract_param_types(lines: list[str]) -> list[str]:
    for line in lines:
        line = line.strip()
        if line.startswith("def "):
            start = line.index("(") + 1
            end = line.rindex(")")
            params_str = line[start:end]
            if not params_str.strip():
                return []
            params = [p.strip() for p in params_str.split(",")]
            result = []
            for p in params:
                if ":" in p:
                    result.append(p.split(":")[1].strip())
                else:
                    result.append("int")
            return result
    return []


def _extract_call(user_code: str, input_str: str) -> str:
    for line in user_code.splitlines():
        line = line.strip()
        if line.startswith("def "):
            func_name = line[4:line.index("(")]
            return f"{func_name}({input_str})"
    return f"({input_str})"


def _compare_result(actual: str, expected: str) -> bool:
    try:
        if expected.lstrip("-").isdigit():
            return actual == repr(int(expected))
    except (ValueError, SyntaxError):
        pass
    return actual == repr(expected)


def _tokenize_args(input_str: str) -> list[str]:
    parts = []
    for p in input_str.split(","):
        p = p.strip()
        parts.append(p)
    return parts


def _build_result(results: list, passed: int) -> dict:
    total = len(results)
    return {
        "passed": passed,
        "total": total,
        "score": passed / total if total > 0 else 0.0,
        "results": results,
    }


_LANG_RUNNERS = {
    "python": _run_python_tests,
    "py": _run_python_tests,
    "cpp": _run_cpp_tests,
    "c++": _run_cpp_tests,
    "c": _run_c_tests,
    "java": _run_java_tests,
    "javascript": _run_js_tests,
    "js": _run_js_tests,
}
