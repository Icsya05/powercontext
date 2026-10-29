# 背景
在真实业务系统中，大量重要信息并不是结构化地存放在表格字段里，而是存在于合同、报告、工单、说明文档、日志文本等非结构化内容中。传统数据库擅长管理结构化数据，但面对这些文档内容时，往往只能提供存储、检索和简单匹配能力，无法直接理解文档语义，更难完成摘要、抽取、分类、问答等智能处理任务。

随着大模型能力的发展，一个重要趋势是让 AI 能力进入数据库执行流程：用户不仅可以查询数据，还可以在 SQL 或数据库函数中直接调用模型，对文档内容进行理解和处理。Document AI Function 正是这个方向上的探索，它把模型能力包装成数据库可调用的函数，使数据库从“存储和查询数据”进一步走向“理解和处理数据”。

本题希望同学们理解 AI Function 在数据库系统中的价值：它不是简单地在应用层调一次模型，而是要考虑函数接口、执行链路、数据流转、结果返回、错误处理和系统集成等问题。通过这个题目，同学们可以体会 AI 能力如何真正嵌入数据库内核和查询流程。

# 题目介绍
本题包含两个AI FUNCTION的实现：

1. LOAD_FILE: 导入本地文件到seekdb
2. AI_SPLIT_DOCUMENT: 对text或者markdown进程切分

## LOAD_FILE
### 语法
```java
BLOB LOAD_FILE(location_name varchar, file_name varchar)
```

输入参数说明：

`location_name`：外部存储对应的location对象名字。

`file_name`：外部存储里的文件名字。

返回值说明：

输出外部文件转换成的blob格式数据

### 使用方法
```plain
-- 注册location
CREATE LOCATION lf_loc URL = 'file:///xxxxxx';

-- 使用load_file，返回BLOB
SELECT load_file('lf_loc', 'hello.txt');

-- 查看文件的大小
SELECT length(load_file('lf_loc', 'hello.txt'));
```

### 测试
mysqltest的测试用例在`tools/deploy/mysql_test/test_suite/ai_funcs/t/load_file.test`

## AI_SPLIT_DOCUMENT
### 语法
新增 AI_SPLIT_DOCUMENT算子，功能是切分文档内容，输出一张表用于记录切分内容。

```sql
TABLE AI_SPLIT_DOCUMENT(CONTENT TEXT, [parameters] Json) [AS] [alias_name]
```

parameters 参数支持：

```java
type：text / markdown，默认为 markdown
by：word/sentence，表示切分单位是词数还是句子数，默认为 wod
max：表示每个chunk最切分的词（或者语句）数，默认为 256
overlap：相邻chunk之间有最多交叉多少词（或者句子数）
```

输入参数说明：

`content`: 待切分的数据内容，默认认为content输入是markdown格式的文本字符串。

`parameters`：参数配置项，可选项，用于详细配置相关内容。

输出格式：输出一个表，每行输出有四列数据

| **CHUNK_ID (int)** | **CHUNK_OFFSET(int)** | **CHUNK_LENGTH(int)** | **CHUNK_TEXT(varchar)** |
| --- | --- | --- | --- |
| 文档切片的id | 文档切片开始位置相对于整个doc的offset | 文档切片的length | 文档切片的内容 |

### 使用方法
```plain
-- one sentence per chunk
SELECT chunk_id, chunk_text
FROM AI_SPLIT_DOCUMENT('First sentence. Second sentence. Third sentence.',
                       '{"type":"text","by":"sentence","max":1}');
-- 0 | First sentence.
-- 1 | Second sentence.
-- 2 | Third sentence.

-- two sentences per chunk (max = 2)
SELECT chunk_id, chunk_text
FROM AI_SPLIT_DOCUMENT('S1 one. S2 two. S3 three. S4 four. S5 five.',
                       '{"by":"sentence","max":2}');
-- 0 | S1 one. S2 two.
-- 1 | S3 three. S4 four.
-- 2 | S5 five.

-- word window: 3 words per chunk, repeating 1 word from the previous chunk (overlap)
SELECT chunk_id, chunk_text
FROM AI_SPLIT_DOCUMENT('alpha beta gamma delta epsilon zeta eta theta',
                       '{"by":"word","max":3,"overlap":1}');
-- 0 | alpha beta gamma
-- 1 | gamma delta epsilon
-- 2 | epsilon zeta eta
-- 3 | eta theta

-- markdown: each chunk carries its section heading (the "\n" is a real newline)
SELECT chunk_id, chunk_text
FROM AI_SPLIT_DOCUMENT('# Section A\nThis is content. More here.\n# Section B\nSecond section.',
                       '{"type":"markdown","by":"sentence","max":1}');
-- 0 | "# Section A" + newline + "This is content."
-- 1 | "# Section A" + newline + "More here."
-- 2 | "# Section B" + newline + "Second section."

```

### 测试
mysqltest的测试用例在`tools/deploy/mysql_test/test_suite/ai_funcs/t/ai_split_document.test`
