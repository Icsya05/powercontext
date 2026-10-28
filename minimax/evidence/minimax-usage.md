# MiniMax 开发记录

下表是模块实际发出的 MiniMax 调用。`request_id` 来自 MiniMax 服务端，
`usage` 是服务端返回的 token 用量。

| 时间 | 类型 | request_id | 模型 | usage |
| --- | --- | --- | --- | --- |
| 2026-10-28T21:55:48 | minimax.call | `073131e3d08ed3e4ee6625246e88955f` | MiniMax-M3 | `{"total_tokens": 210, "total_characters": 0, "prompt_tokens": 198, "completion_tokens": 12, "completion_tokens_details": {"reasoning_tokens": 8}, "prompt_tokens_details": {"cached_tokens": 128}}` |
| 2026-10-28T21:56:48 | minimax.call | `073132202ce811a8d445908a43686809` | MiniMax-M3 | `{"total_tokens": 208, "total_characters": 0, "prompt_tokens": 198, "completion_tokens": 10, "completion_tokens_details": {"reasoning_tokens": 6}, "prompt_tokens_details": {"cached_tokens": 197}}` |
| 2026-10-28T22:04:32 | minimax.call | `073133a2c2b27255e8b8242a9887f883` | MiniMax-M3 | `{"total_tokens": 19106, "total_characters": 0, "prompt_tokens": 10914, "completion_tokens": 8192, "completion_tokens_details": {"reasoning_tokens": 7633}, "prompt_tokens_details": {"cached_tokens": 128}}` |
| 2026-10-28T22:04:32 | testgen.requested | `073133a2c2b27255e8b8242a9887f883` | MiniMax-M3 | `{"total_tokens": 19106, "total_characters": 0, "prompt_tokens": 10914, "completion_tokens": 8192, "completion_tokens_details": {"reasoning_tokens": 7633}, "prompt_tokens_details": {"cached_tokens": 128}}` |
| 2026-10-28T22:19:35 | minimax.call | `07313718b044cff4413f7ad7fe602a67` | MiniMax-M3 | `{"total_tokens": 19389, "total_characters": 0, "prompt_tokens": 10914, "completion_tokens": 8475, "completion_tokens_details": {"reasoning_tokens": 7752}, "prompt_tokens_details": {"cached_tokens": 10913}}` |
| 2026-10-28T22:19:35 | testgen.requested | `07313718b044cff4413f7ad7fe602a67` | MiniMax-M3 | `{"total_tokens": 19389, "total_characters": 0, "prompt_tokens": 10914, "completion_tokens": 8475, "completion_tokens_details": {"reasoning_tokens": 7752}, "prompt_tokens_details": {"cached_tokens": 10913}}` |
| 2026-10-28T22:23:27 | minimax.call | `073137f831081b11882252e452739c01` | MiniMax-M3 | `{"total_tokens": 24275, "total_characters": 0, "prompt_tokens": 10907, "completion_tokens": 13368, "completion_tokens_details": {"reasoning_tokens": 13136}, "prompt_tokens_details": {"cached_tokens": 128}}` |
| 2026-10-28T22:23:27 | patch.requested | `073137f831081b11882252e452739c01` | MiniMax-M3 | `{"total_tokens": 24275, "total_characters": 0, "prompt_tokens": 10907, "completion_tokens": 13368, "completion_tokens_details": {"reasoning_tokens": 13136}, "prompt_tokens_details": {"cached_tokens": 128}}` |
| 2026-10-28T22:27:12 | minimax.call | `07313903440ea21ed089543400102f40` | MiniMax-M3 | `{"total_tokens": 20328, "total_characters": 0, "prompt_tokens": 13715, "completion_tokens": 6613, "completion_tokens_details": {"reasoning_tokens": 6409}, "prompt_tokens_details": {"cached_tokens": 128}}` |
| 2026-10-28T22:27:12 | patch.requested | `07313903440ea21ed089543400102f40` | MiniMax-M3 | `{"total_tokens": 20328, "total_characters": 0, "prompt_tokens": 13715, "completion_tokens": 6613, "completion_tokens_details": {"reasoning_tokens": 6409}, "prompt_tokens_details": {"cached_tokens": 128}}` |
| 2026-10-28T22:28:49 | minimax.call | `07313971e3c2dc50510f73a39a5ef99c` | MiniMax-M3 | `{"total_tokens": 21182, "total_characters": 0, "prompt_tokens": 14878, "completion_tokens": 6304, "completion_tokens_details": {"reasoning_tokens": 6035}, "prompt_tokens_details": {"cached_tokens": 128}}` |
| 2026-10-28T22:28:49 | patch.requested | `07313971e3c2dc50510f73a39a5ef99c` | MiniMax-M3 | `{"total_tokens": 21182, "total_characters": 0, "prompt_tokens": 14878, "completion_tokens": 6304, "completion_tokens_details": {"reasoning_tokens": 6035}, "prompt_tokens_details": {"cached_tokens": 128}}` |
| 2026-10-28T22:32:55 | minimax.call | `07313a5bec51c59d72b86e7092cd7c84` | MiniMax-M3 | `{"total_tokens": 25043, "total_characters": 0, "prompt_tokens": 18328, "completion_tokens": 6715, "completion_tokens_details": {"reasoning_tokens": 6460}, "prompt_tokens_details": {"cached_tokens": 128}}` |
| 2026-10-28T22:32:55 | patch.requested | `07313a5bec51c59d72b86e7092cd7c84` | MiniMax-M3 | `{"total_tokens": 25043, "total_characters": 0, "prompt_tokens": 18328, "completion_tokens": 6715, "completion_tokens_details": {"reasoning_tokens": 6460}, "prompt_tokens_details": {"cached_tokens": 128}}` |
| 2026-10-28T22:36:54 | minimax.call | `07313b64674a225f54f73db239e8b4ea` | MiniMax-M3 | `{"total_tokens": 20861, "total_characters": 0, "prompt_tokens": 17513, "completion_tokens": 3348, "completion_tokens_details": {"reasoning_tokens": 2626}, "prompt_tokens_details": {"cached_tokens": 128}}` |
| 2026-10-28T22:36:54 | testgen.requested | `07313b64674a225f54f73db239e8b4ea` | MiniMax-M3 | `{"total_tokens": 20861, "total_characters": 0, "prompt_tokens": 17513, "completion_tokens": 3348, "completion_tokens_details": {"reasoning_tokens": 2626}, "prompt_tokens_details": {"cached_tokens": 128}}` |

## 每次调用的提问与回答

### 2026-10-28T21:55:48  `073131e3d08ed3e4ee6625246e88955f`

回答（截断到 3000 字符）：

```
<think>We need answer exactly OK due developer.</think>

OK
```

### 2026-10-28T21:56:48  `073132202ce811a8d445908a43686809`

回答（截断到 3000 字符）：

```
<think>We need obey exactly OK.</think>

OK
```

### 2026-10-28T22:04:32  `073133a2c2b27255e8b8242a9887f883`

回答（截断到 3000 字符）：

```
<think>We need produce exactly one fenced block complete file content tests/test_matches.py. Need carefully infer project style, imports, paths. Need test requirements R1-R6 one per where sensible. Must fail current code with unknown function error, not collection/import error. Need likely unittest style existing project. Need ensure all tests fail currently? Requirement A2 says before implementation target test must fail because R1 unimplemented, error contains Unknown function: matches(). Ideally each test invokes matches and current code yields UnknownFunctionError. We need construct file. Need inspect provided context only, perhaps project location sample_project/jmespath. They ask file inside project jmespath likely tests/test_matches.py. Existing style unittest. Imports likely `import unittest`, `import jmespath`, `from jmespath import exceptions`. We need test exactly requirements.

Need reason jmespath syntax and exception messages. R1 exactly two strings:
- Arity wrong: perhaps test too few and too many, both ArityError. Need query syntax valid. `matches(@)` one arg, `matches(@, @, @)` three. But current implementation unknown function will arise likely at evaluation after arity? Function registry lookup first, so unknown.
- type wrong subject and pattern: `matches(@, 'foo')` with nonstring, `matches('foo', @)` pattern nonstring. Raise JMESPathTypeError.
"one test per requirement where makes sense" Could one test per R requirement. R1 test can include subTest perhaps Python version? Upstream supports old Python perhaps project old version; use unittest likely Python3. Could avoid subTest compatibility concerns? v1.1.0 dates supports Python 2 maybe tests styles Python 2 compatible. But task current likely modern. Existing style unittest. A test per R1-R6.

R2 true false and genuine bool. Could test direct expression `matches('abc', 'b')`, likely JMESPath supports string literals? Existing parser syntax supports `'abc'` likely yes. JMESPath examples use `matches(name, '^a')`; raw string literals in JMESPath use backticks for JSON literals, but single-quoted raw string literals are also standard JMESPath. Need use backticks perhaps safest: `matches(\`abc\`, \`b\`)`. Yet quoted string parsing and escaping? yes.

Test result `self.assertIs(result, True)` and false. R3 re.search semantics across examples and constructs `^ $ .* [0-9] \+`. Need cover. Could have one test method assertions:
`matches('abc','b') True`
`matches('abc','^a') True`
`matches('abc','^b') False`
Maybe regex semantics all listed perhaps cover `.*`, `[0-9]`, `\+`. R3 says therefore syntax works, acceptance asks regex semantics. We should comprehensively test:
- search arbitrary position b
- anchor ^a
- anchor ^b false
- `.*` likely true for anything maybe empty too
- `[0-9]` finds digit
- `\+` finds plus literal. Perhaps escape query raw strings. JMESPath raw string literal rules likely `'\+'` accepted as raw literal preserving slash. Single quoted raw strings support backs
```

### 2026-10-28T22:19:35  `07313718b044cff4413f7ad7fe602a67`

回答（截断到 3000 字符）：

```
<think>We need craft exact one fenced block complete test file. Need understand project style, likely unittest. Need ensure imports standard/project. Need tests R1-R6 each where makes sense. Must fail current code with clear Unknown function style, not collection/import error. Important import behavior: likely import jmespath.exceptions? Existing package maybe `from jmespath import exceptions` or `import jmespath.exceptions`. Need construct file without importing nonexistent matches direct. Use `import jmespath` and `from jmespath import exceptions` likely package exposes? We need inspect described upstream v1.1.0 style. User gives tests. We need answer only fenced block. Need thoughtfully cover each R.

Potential challenge current code raises UnknownFunctionError at test execution. If module imports fine. Tests can use unittest.

R1 exact two string args:
- arity errors one and three arguments. `jmespath.search('matches(@)', 'subject')` parser perhaps function invocation syntax and type. Unknown function happens before arity currently, after implementation arity.
- Non-string subject and pattern produce JMESPathTypeError. Test perhaps one test each? Requirement one per numbered requirement where makes sense. Could make TestMatches with 6 test methods mapping R1-R6. R1 can include subTests (Py version? likely Python modern). Project old perhaps unittest. Need perhaps separate tests for subject and pattern and arity. One test per numbered requirement where makes sense doesn't insist exactly one. We should cover robustly.

R2 hit/miss true false actual bool. Use `self.assertIs(result, True/False)`, and equals. Query literals. Syntax `matches(\`abc\`, \`b\`)`. JMESPath raw strings. Could call `jmespath.search('matches(`abc`, `b`)', {})`.

R3 Python re.search semantics. Need ensure patterns quoted and escape behavior. Test examples b, ^a, ^b, perhaps `$`, `.*`, `[0-9]`, `\+`. Need cover regex not full. Requirement explicitly says syntax examples. Could one method with several assertions:
search matches abc b true
^ a true, ^b false
abc `.*` true
abc123 `[0-9]` true
abc `a\+` false maybe escaping literal plus. Need understand JMESPath string raw literal backslash preserved? In raw string, `a\+` likely yes. Lexer handling. Could test pattern `\d`? JMESPath backtick string likely parser supports raw. Python re semantics. Need avoid issue JSON escapes? Backtick literal probably `\\` handling? Let's inspect upstream jmespath 1.1 parser lexer knowledge. JMESPath raw string literals enclosed backticks, contents interpreted exactly? Lexer `_consume_raw_string`: while current != '`'; if backslash? likely preserve. So fine.

R4 invalid regex `[`. `jmespath.search('matches(`abc`, `[`)', {})`; should raise JMESPathTypeError. Error contains function name `matches()` and pattern value `[`. We need assert. Requirement says error info includes function name matches() and offending pattern value. Since `JMESPathTypeError` constructor perhaps signature. Need not assum
```

### 2026-10-28T22:23:27  `073137f831081b11882252e452739c01`

回答（截断到 3000 字符）：

```
<think>We need produce exactly one fenced block unified diff only, path specified. Need infer implementation. Need modify functions.py likely import re and add method. User says code has to change only functions.py; though A1 says add tests, but developer explicitly says given code that has to change? Final requested unified diff implementing task. Rules "Change only what specification asks". They mandate diff paths only functions.py based developer: unified diff must use paths minimax/sample_project/jmespath/jmespath/functions.py. So no test file diff. Need implement matching spec robustly, error message conventions.

Need inspect likely file content from supplied. Need determine imports top. Upstream jmespath.py v1.1.0 functions.py. Let's recall:

import base64
import json
import math
import re

from botocore.compat import six

from .exceptions import ArityError
...

Actually jmespath package old version. Search memory of jmespath 1.1.0 functions.py source. likely:

import base64
import json
import math
import re

from . import exceptions
from .compat import string_type


def signature(*arguments):
...

Maybe re already imported? Need know. JMESPath 1.1.0 code perhaps:

import base64
import json
import math
import re

from . import exceptions
from .compat import string_type

PY2 = sys.version_info[0] == 2
...
Functions methods include base64_encode, base64_decode, ceil, floor? Supplied snippet omitted those? It says existing 23 built-ins. Provided Functions class excerpt starts abs avg etc but no base64 perhaps perhaps omitted in code text? Let's find exact upstream source mentally. jmespath.py v1.1.0 functions.py:

# Copyright...
import base64
import json
import math
import re

from . import exceptions
from .compat import string_type

PY2 = sys.version_info[0] == 2
...
Actually jmespath package old version. Search memory of jmespath 1.1.0 functions.py source. likely:

import base64
import json
import math
import re

from . import exceptions
from .compat import string_type


def signature(*arguments):
    def _record_signature(func):
        func.signature = arguments
        return func
    return _record_signature


def get_methods(cls):
    for method_name in dir(cls):
        try:
            method = getattr(cls, method_name)
        except AttributeError:
            continue
        if inspect.ismethod(method) or inspect.isfunction(method):
            yield method_name, method


class FunctionRegistry(type):
...
class Functions(metaclass=FunctionRegistry):
...
    @signature({'types': ['string']}, {'types': ['string']})
    def _func_starts_with(self, search, suffix):
...
No built-in matches in upstream likely. re import may already be present for base64? Let's inspect upstream 1.1.0 perhaps exact:

import base64
import json
import math
import re

from . import exceptions
from .compat import string_type

def signature...
...
    @signature({'types': ['string']})
    def _func_base64_decode(self, arg):
        return base64.b64decode(arg
```

### 2026-10-28T22:27:12  `07313903440ea21ed089543400102f40`

回答（截断到 3000 字符）：

```
<think>We need produce exactly one fenced block unified diff path. Need infer current repository state? Previous attempt applied likely functions.py now has method but missing import re. User asks corrected diff. We must output diff against repository-root? The specified path minimax/sample_project/jmespath/jmespath/functions.py, though task Code path sample_project/jmespath perhaps root is minimax? Developer explicitly unified diff path must be minimax/sample_project/jmespath/jmespath/functions.py. Need include import re and perhaps fix re.search argument order! Failure shows prior implementation `re.search(subject, pattern)` wrong Python signature: re.search(pattern, string). Had re imported it'd compile subject 'abc' and search in pattern 'b', reversing semantics! Existing failure couldn't reach due NameError. Need corrected implementation likely import re and `re.search(pattern, subject)`. Need assess current file baseline and previous applied patch context. We don't have tools, but supplied full functions.py original and previous method snippet. Need formulate diff likely from current state (with method inserted) or from original expected patch? They ask produce corrected diff, patch application likely against current repository which contains prior attempt? Usually benchmark asks output diff; evaluator applies generated diff perhaps to current state? The prompt says earlier diff was applied and acceptance failed, likely workspace now includes attempt1 changes. Need diff current -> corrected. Thus include import re and change method argument order. Need know line exact and import placement. Original functions.py top likely:

import math
import json

from jmespath import exceptions
from jmespath.utils import get_methods

Maybe inspect known jmespath.py v1.1.0 source. functions.py starts:
```
import math
import json

from jmespath import exceptions
from jmespath.utils import get_methods

STRING_TYPE = str
...
```
Could add `import re`. Previous attempt likely method around line 228 after starts_with, as failure line 232. Existing code perhaps currently:
```
import math
import json
...
    @signature...
    def _func_matches(self, subject, pattern):
        try:
            return re.search(subject, pattern) is not None
        except re.error:
            raise exceptions.JMESPathTypeError(
                'matches', pattern, 'string', ['string'])
```
Need determine error message exact requirements. R4: JMESPathTypeError, info includes function name matches() and pattern value. `JMESPathTypeError` constructor likely takes function_name, value, actual_type, expected_types and formats. Prior method likely used:
```
raise exceptions.JMESPathTypeError(
    'matches', pattern, 'string', ['string'])
```
Would output invalid type for value: [ and received string expected string—not semantically perhaps okay but required function name and pattern. Let's inspect likely test expectations from supplied failure. tests/test_matches.py exists due previous p
```

### 2026-10-28T22:28:49  `07313971e3c2dc50510f73a39a5ef99c`

回答（截断到 3000 字符）：

```
<think>We need answer exactly one fenced block containing unified diff, path repository-root relative minimax/sample_project/jmespath/jmespath/functions.py. Need implement. Need inspect original? User supplied source likely original imports omitted top. Need determine exact file content/import style and exception constructor. Need produce diff against original, likely add import re and method. Previous attempt error says real line 'from jmespath.compat import get_methods'. We need infer functions.py top. Let's locate mentally upstream jmespath.py v1.1.0 functions.py. Likely:

import json
import math

from jmespath import exceptions
from jmespath.compat import get_methods
from jmespath.exceptions import ArityError
from jmespath.utils import ...

Actually upstream. Let's search from knowledge. jmespath package old. functions.py likely:

import json
import math

from jmespath import exceptions
from jmespath.compat import get_methods

try:
    STRING_TYPE = basestring
except NameError:
    STRING_TYPE = str

TYPES_MAP = {
    'bool': 'boolean',
    'dict': 'object',
    'float': 'number',
    'int': 'number',
    'list': 'array',
    'NoneType': 'null',
    'str': 'string',
    'unicode': 'string',
}

REVERSE_TYPES_MAP = {
    'boolean': ['bool'],
    'object': ['dict'],
    'array': ['list'],
    'string': ['str', 'unicode'],
    'number': ['int', 'float'],
    'null': ['NoneType'],
}

Need add `import re` likely standard import style. Then method near starts_with? Specs say only through one decorated method. We should add:
    @signature({'types': ['string']}, {'types': ['string']})
    def _func_matches(self, subject, pattern):
        try:
            return re.search(pattern, subject) is not None
        except re.error:
            raise exceptions.JMESPathTypeError(
                'matches', pattern, 'string', ['string'])

But R4 error message must contain function name matches() and pattern value. JMESPathTypeError constructor formats function name with (), invalid type for value, expected types, received type. If call with function_name 'matches', actual pattern '[', actual type perhaps 'string' and expected ['string'] gives:
Invalid type for function matches(), expected one of: ['string'], received: "string": invalid type for value: [
This includes function and value, but semantically weird expected/received both string. R4 only requires JMESPathTypeError, message contains matches() and pattern value. Existing error style. We need know exceptions.JMESPathTypeError implementation. Likely:

class JMESPathTypeError(JMESPathError):
    def __init__(self, function_name, actual_value, actual_type, expected_types):
        super(...).__init__(
            "Invalid type for function %s(), expected one of: %s, "
            "received: %s" % (function_name, expected_types,
                              json.dumps(actual_type)))
        self.message = (
            "Invalid type for function %s(), expected one of: %s, "
            "received: %s: inv
```

### 2026-10-28T22:32:55  `07313a5bec51c59d72b86e7092cd7c84`

回答（截断到 3000 字符）：

```
<think>We need produce exactly one fenced block unified diff. Need carefully implement. Need inspect specs and exception class format perhaps provided current only functions. Need derive correct invalid regex JMESPathTypeError message includes matches() and pattern value. Need know exceptions.py API. User says exact current functions, tests provided. We need patch only specified path minimax/sample_project/jmespath/jmespath/functions.py. Need import re and method. But prior attempt issue re.search arguments reversed perhaps traceback showed `re.search(subject, pattern)`! In Python re.search(pattern, string). Their attempt likely had reversed. Need ensure pattern first, subject second. Also invalid regex error transformed to JMESPathTypeError with message containing function name matches() and pattern. Need inspect exceptions.py conventions perhaps infer. We have tool? No explicit tools available, only reasoning. We can perhaps use provided repository context mentally. Need output diff with proper hunk lines. Add import re likely `import re` near imports. Add method around starts_with or contains. Signature exactly. Implement:

    @signature({'types': ['string']}, {'types': ['string']})
    def _func_matches(self, subject, pattern):
        try:
            return re.search(pattern, subject) is not None
        except re.error:
            raise exceptions.JMESPathTypeError(
                'matches', pattern, 'string', ['string'])

Would exception message include "matches()" and "value: ["? Need inspect JMESPathTypeError constructor behavior from upstream jmespath.py v1.1.0. Likely:

class JMESPathTypeError(TypeError):
    def __init__(self, function_name, value, actual_type, expected_types):
        super(...).__init__(
            "Invalid type for %s(), expected one of: %s, received: %s" % ...)
Maybe exact format test expects "invalid type for value: 42". Let's retrieve upstream jmespath exceptions knowledge. I know Python jmespath library. Modern jmespath exceptions.py:

class JMESPathError(Exception):
    pass

class UnknownFunctionError(JMESPathError):
    def __init__(self, function_name):
        super().__init__('Unknown function: %s()' % function_name)

class ArityError(JMESPathError):
    def __init__(self, expected, received, function_name):
        super().__init__(
            'Expected %s arguments for function %s(), received %s' %
            (expected, function_name, received))

class VariadicArityError(ArityError):
...

class JMESPathTypeError(JMESPathError):
    def __init__(self, function_name, value, actual_type, expected_types):
        super().__init__(
            'Invalid type for %s(), expected one of: %s, received: %s' %
            (function_name, expected_types, actual_type))
Maybe current v1.1 old style? Tests expect lowercase "invalid type for value: 42", expected one of, received number. Likely constructor automatically includes value. Let's search memory. jmespath.py project older exceptions.py maybe:

class JMES
```

### 2026-10-28T22:36:54  `07313b64674a225f54f73db239e8b4ea`

回答（截断到 3000 字符）：

```
<think>We need answer exactly fenced block complete tests/test_matches.py. Need carefully formulate corrected file. Need obey only stdlib/project. Must fail current code base? Interesting exact current content includes implementation already! Yet developer says must fail current code because behavior not implemented, but user states current functions.py has _func_matches already. Maybe perhaps test expected to catch flaw? Need inspect supplied context. Current implementation has matches registered, likely tests mostly pass except escaping. But developer explicitly rule test file must fail current code with clear unknown function style error, not collection/import. Contradiction: current code appears implemented. Perhaps "current code base" conceptual before implementation? They included exact current content under change including implementation oddly. Maybe implementation present and target tests need test. Yet test requested acceptance file. Need produce exactly one fenced block no outside.

We need understand likely expected content based explicitly provided "Tests that verify behaviour" and previous version. We should write complete file with imports unittest, jmespath, exceptions, six tests. Fix R3 escaping JSON legal: backtick literal should be `"\\\\+"`? Let's reason Python source representation and JMESPath lexer.

Want JMESPath expression to contain backtick literal `\+` lexeme such that JSON parser sees valid escape for backslash then plus. JSON string source inside backticks needs "\\+": characters backtick, backslash, backslash, plus, backtick. In Python regular string, to yield two backslashes, source needs `\\\\` (four backslashes). E.g. Python:
jmespath.search("matches(`a+b`, `\\\\+`)", {})
Python value `matches(`a+b`, `\\+`)`, lexer lexeme `\\+`, json.loads -> `\+`, regex literal plus. Or raw Python r"matches(`a+b`, `\\+`)" yields two backslashes and JSON valid. The broken was r"...`\+`" one slash invalid JSON. Correct likely r"matches(`a+b`, `\\+`)" (raw with two slash). Could also avoid regex backslash escaping issue by use JSON string pattern with Unicode? Need test semantics \+ explicitly. Use `'matches(`a+b`, `\\\\+`)'` or r"matches(`a+b`, `\\+`)". Need ensure expected.

Need perhaps include exact content shown from source? They say previous version wrong, corrected complete file. Could simply output file matching listed test code with corrected R3. But developer general rule says one test per numbered req, every R1-R6. Six methods does. Also "must fail on current code base because specified behavior not implemented yet - clear unknown function style error." If implementation current means tests won't unknown function. But perhaps hidden evaluator resets code to original no matches, then this test will fail UnknownFunctionError. We should make sure first test triggers unknown function error in current (preimplementation) and not assert collection. Yes search at runtime raises unknown function, but with `assertRaises(ArityErro
```
