本文介绍如何在GitHub上创建私有仓库，并将seekdb/powercontext代码提交到自己的仓库中，然后在大赛中进行测试。

seekdb仓库地址：[https://github.com/oceanbase/seekdb](https://github.com/oceanbase/seekdb)

powercontext仓库地址：[https://github.com/oceanbase/powercontext](https://github.com/oceanbase/powercontext)

## GitHub 私有仓库创建
**NOTE** 一定要使用私有仓库进行测试。

首先你要有一个自己的GitHub账号。账号的注册流程比较简单，没有账号的同学登录GitHub网站创建即可。

1. 登录GitHub网站，并登录自己的账号
2. 在网站右上角点击 "Import Repository"

![](https://cdn.nlark.com/yuque/0/2026/png/28749819/1792568558670-f5d4f849-1b3f-486b-af67-a11c744c289d.png)

3. 填写导入表单

在"Your old repository's clone URL"项目中填写仓库的地址：

```plain
https://github.com/oceanbase/seekdb
```

![](https://cdn.nlark.com/yuque/0/2026/png/28749819/1792568995408-13f51336-3116-48c6-862a-d8eb33e95f5b.png)

4. 点击"Begin import"按钮，开始导入仓库

导入会花费一定时间，导入完成后，可以看到：

![](https://cdn.nlark.com/yuque/0/2026/png/28749819/1792569291729-a57cdeef-e8a2-40a8-bcca-176074626057.png)

5. 查看仓库首页

点击"Code" 标签，就可以进入到仓库首页。

![](https://cdn.nlark.com/yuque/0/2026/png/28749819/1792569574011-2b270f6b-d385-4293-83d9-ab81d67ed115.png)

## 仓库权限设置
到此为止，已经创建完了私有仓库，并导入了代码。但是此时官方并没有权限查看你的代码，接下来需要**生成一个token并将带token的地址填写到参赛信息中**。

### 生成token
1. 在GitHub页面，点击个人头像，选择"Settings"，进入个人设置页面。

![](https://cdn.nlark.com/yuque/0/2026/png/28749819/1792569679061-aa108dcc-ea66-41af-b8c5-af0f2281804e.png)

2. 接着在左侧导航栏中选择"Developer settings"，进入开发者设置页面。 ![](https://cdn.nlark.com/yuque/0/2026/png/28749819/1792569766966-346e151d-40fd-4fff-94da-bfe5432f1589.png)
3. 找到生成新token的页面。

![](https://cdn.nlark.com/yuque/0/2026/png/28749819/1792570147554-795ea277-520a-4bce-9a1e-48369fb703de.png)

4. 填写token的信息，生成token。

![](https://cdn.nlark.com/yuque/0/2026/png/28749819/1792571081347-796ebf3d-e8bd-44c5-b121-f22df65c86af.png)

5. 生成token后要第一时间保存，离开页面后将无法再次查看。

![](https://cdn.nlark.com/yuque/0/2026/png/28749819/1792571175269-7a3090ca-e4f1-4176-8239-4ebcae086960.png)

6. 验证token是否生效 执行 git clone 命令，URL中带上 username和token，如果能够正常clone，则说明token生效。

```plain
git clone https://`your-github-username`:`github_pat_your-github-token`@github.com/`repo-owner`/`repo-name`
```

+ your-github-username 替换成你的GitHub用户名
+ github_pat_your-github-token 替换成你的生成的token
+ repo-owner 替换成你的仓库所属者，通常也是你的GitHub用户名
+ repo-name 替换成你的仓库名，比如 seekdb-2026

比如：

```plain
git clone https://LINxiansheng:github_pat_token@github.com/LINxiansheng/seekdb-2026
```

一个clone成功的例子

![](https://cdn.nlark.com/yuque/0/2026/png/28749819/1792571888275-3cd108fd-d579-424c-aa61-e8a1aa3ad830.png)

**注意：在参赛信息里面填写好user:token的地址**

**比如我添加seekdb赛题仓库地址**

![](https://cdn.nlark.com/yuque/0/2026/png/28749819/1792574045313-a27c22e5-e207-4169-be10-751301cb6ed9.png)

## 提交测试
仓库确认之后，开始提交测试。
