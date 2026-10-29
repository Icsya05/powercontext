> **注意：访问 **[**https://github.com/oceanbase/powercontext/tree/2026-competition**](https://github.com/oceanbase/powercontext/tree/2026-competition)** 获取基线分支和判题相关的公开资产，在测评平台提交时的分支/commit hash 建议基于此分支进行开发。**
>
> **参考资料：**
>
> + [GitHub在大赛中的使用说明](https://oceanbase.yuque.com/org-wiki-obtech-vh7w9r/hc3pio/qs1povt8zbza6hts)
> + [比赛仓库地址](https://oceanbase.yuque.com/org-wiki-obtech-vh7w9r/hc3pio/brxxufkegusa86hl)
>

| 项目 | 内容 |
| --- | --- |
| 编号 | `setup-00-repository-fork` |
| 总分 | 10 分 |
| 任务 | 导入 PowerContext 并授予评测读取权限；已有公开 Fork 也可提交 |
| 提交产物 | `https://github.com/OWNER/REPOSITORY` |
| 上游仓库 | [oceanbase/powercontext](https://github.com/oceanbase/powercontext)，GitHub repository ID 为 `1093180734` |
| 冻结基线 | `9db1753434162c0aa7c9f1189a1722e617880a52` |

## 一、题目背景
后续代码题通过产品仓库和 commit 接收实现。参赛者按参赛指南使用 **Import repository（导入仓库）** 准备自己的 PowerContext 参赛仓库，通常将仓库设为私有，并向组织方授予必要的读取权限。已通过 Fork 创建的公开仓库也可直接提交。

本题检查仓库是否可由组织方读取，并保留官方 fork 关联，或在任一分支的提交历史中包含比赛指定的代码基线，满足要求即可获得准备题的 **10 分**。仓库名称和分支名称不限，可直接使用已有分支，无需创建判题专用分支、修改代码或新增 commit；公开或私有本身不影响得分。

## 二、题目内容
使用 GitHub Import repository 导入 PowerContext 并保留提交历史，提交仓库的 HTTPS URL。私有仓库须提前向组织方授予评测所需的读取权限；已有的公开 Fork 无需重新导入。无需新建判题专用分支，也不要求修改代码、创建 PR 或提交新 commit。

组织方在接收提交时核对以下条件：

1. 仓库存在，组织方具有读取仓库元数据和所需提交历史的权限；公开仓库和已授权的私有仓库均可。
2. 提交仓库不是官方上游仓库本身。
3. 满足以下任一来源条件：GitHub 的 `fork=true` 且 `source.id=1093180734`；或者仓库至少一个分支的提交历史包含冻结基线 `9db1753434162c0aa7c9f1189a1722e617880a52`，分支当前提交可以就是基线本身。

GitHub 的 `source` 表示整个 fork 网络的源仓库，因此接受间接 fork。导入形成的独立仓库无需具有 `fork` 标记，但须保留相关提交历史；仅复制文件后重建历史不能满足历史校验。接口语义见 [GitHub 仓库 API](https://docs.github.com/en/rest/repos/repos#get-a-repository)及[提交比较 API](https://docs.github.com/en/rest/commits/commits#compare-two-commits)。

准备题的历史证明可以来自仓库中的任意分支，不要求该分支是默认分支或本次代码题的评测分支。代码题仍按提测指定的 branch/commit 执行；未指定版本时解析默认分支并冻结实际版本，准备题不会替参赛者切换分支。

## 三、提交方式
提交仓库 URL，允许末尾的 `.git` 和单个 `/`。URL 不包含认证信息、端口、查询参数、片段或分支路径。私有仓库应通过赛事约定方式为组织方授予读取权限，不将令牌或密码放进 URL。

```latex
https://github.com/participant/powercontext
https://github.com/participant/memory-project.git
```

单独提交本题只需 URL；与代码题一同提交时，版本材料遵循代码题要求。组织方采集证据，参赛者无需生成或上传证据文件。

## 四、评分标准
全部条件满足获得 10 分，否则获得 0 分。仓库名称、分支名称和是否创建新提交不影响本题得分。

组织方保存采集时间、仓库身份、必要元数据和适用的分支历史证明，离线判分及重判均使用同一次证据。后续仓库变化通过新的提测重新采集。

GitHub 的 404 不能区分地址不存在和私有仓库未授权，按采集异常处理，核对地址与权限后重试。超时、限流、认证故障、服务错误或缺失证据同样不直接计 0 分。可读取但不满足来源条件的仓库、格式错误的 URL 和未提交 URL 属于有效失败。

## 五、公开测试与提交前检查
确认组织方可以读取仓库。使用私有仓库时，GitHub API 和 Git 源码拉取均须具有相应权限。

Fork 仓库可通过元数据确认 `source.id`；导入仓库可在某个已获取的分支提交上检查基线祖先关系：

```bash
git merge-base --is-ancestor \
  9db1753434162c0aa7c9f1189a1722e617880a52 \
  "$BRANCH_COMMIT"
```

浅克隆应先补齐相关历史。该检查无需新建分支，也不要求当前源码与基线逐字相同。正式判分仍以组织方保存的可信证据为准，verifier 不访问网络、不运行参赛代码。
