# 背景
全文检索的效果，很大程度上取决于系统是否能够正确理解文本中的“词”。在通用场景下，默认分词器可以处理大量常见语言表达，但在真实业务中，经常会出现专有名词、产品名称、医学术语、金融术语、技术缩写、组织内部黑话等领域词汇。如果这些词被错误切分，后续的索引、召回和排序都会受到影响，用户明明输入了正确关键词，却可能搜不到想要的结果。

例如，一个领域术语如果被拆成多个无意义片段，全文索引中保存的 token 就不再符合用户的真实查询意图。对于数据库系统来说，支持自定义分词词典，就是让用户能够把自己的领域知识注入检索系统，使全文检索从“通用可用”走向“业务好用”。

本题希望同学们理解分词、词典和全文检索质量之间的关系。它看起来像是一个小功能，但背后连接的是文本理解、索引构建、查询解析和业务语义适配。通过这个题目，同学们可以看到：让数据库支持 AI 和全文检索，不只是接入模型，也需要认真处理语言、领域知识和用户查询习惯。

自定义词典（Custom Dictionary）是 OceanBase 全文索引（Full-Text Search）提供的词典扩展机制，允许用户通过自定义词表控制 IK 分词器的分词行为。用户可以添加自定义词汇、停用词和量词，使分词结果更贴合业务场景，提升全文检索的准确性。

## SQL 语法
### 创建词典表
```sql
CREATE TABLE dict_table_name (
  word varchar(length) PRIMARY KEY
) ORGANIZATION INDEX DEFAULT CHARSET = utf8mb4 COLLATE = utf8mb4_general_ci FULLTEXT_DICT = 'Y';
```

**参数说明：**

| 参数 | 说明 | 示例 |
| --- | --- | --- |
| `dict_table_name` | 词典表名称 | `my_dict`、`stopwords`、`quantifiers` |
| `length` | `word` 列的 varchar 长度，取值范围 1~500 | `varchar(100)`、`varchar(500)` |
| `FULLTEXT_DICT = 'Y'` | 必选。标识该表为全文索引词典表 | - |

**示例：**

```sql
-- 创建自定义分词词典表
CREATE TABLE my_dict (
  word varchar(100) primary key
) ORGANIZATION INDEX DEFAULT CHARSET = utf8mb4 COLLATE = utf8mb4_general_ci FULLTEXT_DICT = 'Y';

-- 创建停用词词典表
CREATE TABLE my_stopwords (
  word varchar(100) primary key
) ORGANIZATION INDEX DEFAULT CHARSET = utf8mb4 COLLATE = utf8mb4_general_ci FULLTEXT_DICT = 'Y';

-- 创建量词词典表
CREATE TABLE my_quantifiers (
  word varchar(100) primary key
) ORGANIZATION INDEX DEFAULT CHARSET = utf8mb4 COLLATE = utf8mb4_general_ci FULLTEXT_DICT = 'Y';
```

### 刷新词典缓存
修改词典内容后，执行刷新命令可使变更立即生效：

```sql
ALTER SYSTEM REFRESH FULLTEXT DICT [database_name.]table_name;
```

**支持的表名格式：**

```sql
-- 带数据库名
ALTER SYSTEM REFRESH FULLTEXT DICT mydb.my_dict;

-- 不带数据库名（使用当前数据库）
ALTER SYSTEM REFRESH FULLTEXT DICT my_dict;

-- 双引号引用（带数据库名）
ALTER SYSTEM REFRESH FULLTEXT DICT "mydb.my_dict";

-- 双引号引用（不带数据库名）
ALTER SYSTEM REFRESH FULLTEXT DICT "my_dict";
```

### 创建使用自定义词典的全文索引
通过 `PARSER_PROPERTIES` 子句将全文索引与自定义词典关联：

```sql
-- 通过 ALTER TABLE 添加全文索引
ALTER TABLE table_name ADD FULLTEXT INDEX index_name(column_name)
  WITH PARSER ik PARSER_PROPERTIES=(dict_table='[database_name.]dict_table_name');

-- 通过 CREATE TABLE 内联创建
CREATE TABLE table_name (
  id int PRIMARY KEY AUTO_INCREMENT,
  title varchar(200),
  FULLTEXT INDEX index_name(title) WITH PARSER ik
    PARSER_PROPERTIES=(dict_table='[database_name.]dict_table_name')
) DEFAULT CHARSET = utf8mb4 COLLATE = utf8mb4_bin;
```

**注：****新建全文索引时，系统会主动去尝试加载关联的自定义词典表，此时无需主动refresh亦可使得自定义词典表生效。**

**PARSER_PROPERTIES 支持的配置项：**

| 配置项 | 说明 | 示例 |
| --- | --- | --- |
| `dict_table` | 自定义分词词典表名 | `dict_table='mydb.my_dict'` |
| `stopword_table` | 停用词词典表名 | `stopword_table='mydb.my_stopwords'` |
| `quantifier_table` | 量词词典表名 | `quantifier_table='mydb.my_quantifiers'` |
| `ik_mode` | IK 分词模式：`smart`（默认）或 `max_word` | `ik_mode='max_word'` |

**多配置项组合示例：**

```sql
ALTER TABLE articles ADD FULLTEXT INDEX ft_title(title)
  WITH PARSER ik PARSER_PROPERTIES=(
    dict_table='mydb.my_dict',
    stopword_table='mydb.my_stopwords',
    quantifier_table='mydb.my_quantifiers'
  );
```

### 删除全文索引与词典表
```sql
-- 删除全文索引
ALTER TABLE articles DROP INDEX ft_title;
-- 或
DROP INDEX ft_title ON articles;

-- 删除词典表（必须先删除所有引用该词典的全文索引）
DROP TABLE my_dict;
```

---

## 词典表结构要求
### 必须满足的约束
| 约束 | 说明 |
| --- | --- |
| 列名必须为 `word` | 且为表的唯一列 |
| `word` 列必须为主键 | - |
| `word` 列类型必须为 `varchar` | 不支持 `int`、`text` 等其他类型 |
| 字符集必须为 `utf8mb4` | 不支持 `latin1` 等其他字符集 |
| 必须指定 `ORGANIZATION INDEX` | 使用 IOT（索引组织表）存储模式 |
| 必须设置 `FULLTEXT_DICT = 'Y'` | 标识为全文索引词典表 |
| 仅允许单列 | 不支持额外列 |

### 支持的 collation
词典表的 `word` 列仅支持字符集utf8mb4下的所有字符序：

```sql
-- 注意：当前版本只有IK分词器，其行为为大小写不敏感（统一小写对待）
-- 配置为大小写敏感时，写入词典表的数据必须全是小写，否则可能发生分词不符预期
-- 若确定字典表所有数据英文字符全部为小写，则建议使用大小写敏感的字符序，如utf8mb4_bin
-- 否则，必须使用大小写不敏感的字符序，如默认的utf8mb4_general_ci
CREATE TABLE dict_ci (
  word varchar(100) primary key
) FULLTEXT_DICT = 'Y';  // 建表不指定字符序时默认为utf8mb4_general_ci
```

---

## DDL 限制
当词典表被全文索引引用时，存在以下 DDL 限制：

| 操作 | 是否允许 | 说明 |
| --- | --- | --- |
| 重命名词典表 | **不支持** | 报错 ERROR 1235 |
| 添加列 | **不支持** | 报错 ERROR 1235 |
| 修改列类型 | **不支持** | 报错 ERROR 1235 |
| 删除列 | **不支持** | 报错 ERROR 1235 |
| 重命名列 | **不支持** | 报错 ERROR 1235 |
| 删除被引用的词典表 | **不支持** | 报错 ERROR 4179，需先删除引用的全文索引 |
| 删除未被引用的词典表 | 支持 | - |
| 插入/更新/删除词汇 | 支持 | 修改后需执行 REFRESH 命令才能立即生效 |

---

## 使用流程
### 标准使用流程
推荐的操作步骤如下：

```sql
-- 步骤 1：创建词典表
CREATE TABLE my_dict (
  word varchar(100) primary key
) FULLTEXT_DICT = 'Y';

-- 步骤 2：导入词汇
INSERT INTO my_dict (word) VALUES
('OceanBase'),
('分布式数据库'),
('全文索引');

-- 步骤 3：刷新词典缓存
ALTER SYSTEM REFRESH FULLTEXT DICT mydb.my_dict;

-- 步骤 4：创建业务表
CREATE TABLE articles (
  id int unsigned NOT NULL AUTO_INCREMENT,
  title varchar(200) NOT NULL,
  content text DEFAULT NULL,
  PRIMARY KEY (id)
) DEFAULT CHARSET = utf8mb4 COLLATE = utf8mb4_bin;

-- 步骤 5：创建使用自定义词典的全文索引
ALTER TABLE articles ADD FULLTEXT INDEX ft_title(title)
  WITH PARSER ik PARSER_PROPERTIES=(dict_table='mydb.my_dict');

-- 步骤 6：写入数据
INSERT INTO articles (title, content) VALUES
('OceanBase数据库介绍', 'OceanBase是一款分布式数据库，支持全文索引功能'),
('全文索引使用指南', '本文介绍如何使用全文索引进行查询');

-- 步骤 7：全文检索
SELECT id, title FROM articles
  WHERE MATCH(title) AGAINST('数据库' IN BOOLEAN MODE);
```

### 动态更新词典
词典表支持在运行时动态增删词汇：

```sql
-- 新增词汇
INSERT INTO my_dict (word) VALUES ('新词汇');

-- 刷新使变更生效
ALTER SYSTEM REFRESH FULLTEXT DICT mydb.my_dict;

-- 后续写入的数据将使用更新后的词典进行分词
INSERT INTO articles (title) VALUES ('包含新词汇的标题');

-- 查询即可命中
SELECT * FROM articles WHERE MATCH(title) AGAINST('新词汇' IN BOOLEAN MODE);
```

**注意：** 刷新操作仅影响刷新后新写入的数据。已有数据的索引内容不会自动更新。如需对已有数据使用新词典重新分词，需重建全文索引。

---

## TOKENIZE 函数
`TOKENIZE()` 函数可用于预览分词效果，支持在 `additional_args` 中指定自定义词典：

```sql
-- 同时指定多个词典和 IK 模式
SELECT TOKENIZE('这是非常重要的信息', 'ik',
  '[{"output": "all"}, {"additional_args": [
    {"ik_mode": "max_word"},
    {"dict_table": "mydb.my_dict"},
    {"stopword_table": "mydb.my_stopwords"},
    {"quantifier_table": "mydb.my_quantifiers"}
  ]}]');

-- 对表中列进行分词预览
SELECT TOKENIZE(title, 'ik',
  '[{"output": "all"}, {"additional_args": [{"dict_table": "my_dict"}]}]')
FROM articles;
```

---

## 表名引用规则
### PARSER_PROPERTIES 中的表名
| 格式 | 说明 | 示例 |
| --- | --- | --- |
| `'table_name'` | 使用当前数据库中的词典表 | `dict_table='my_dict'` |
| `'database_name.table_name'` | 使用指定数据库中的词典表 | `dict_table='mydb.my_dict'` |

## 测试
mysqltest的测试用例在`tools/deploy/mysql_test/test_suite/ai_funcs/t/ik_custom_dict.test`。
