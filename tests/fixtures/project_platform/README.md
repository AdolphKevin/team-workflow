# 项目平台脚本的离线输入

JSON 文件是本次任务提供的 GitHub 原始只读响应，未修改正文或字段。
Issue、PR 评论和评审使用 `gh api --paginate --slurp`，外层数组表示分页，不能只取第一页。
运行、任务和产物是对象；测试替身把它们装入分页数组，以对应脚本的同一组参数。
PR 列表未提供独立响应，测试把原始 PR 对象放进列表页；额外分页与异常情况由测试显式构造。

原始样本没有已提交的 PR 评审，也没有产物 ZIP。测试里的评审及其 GraphQL 编辑时间为合成数据，
按 [REST 评审字段](https://docs.github.com/en/rest/pulls/reviews#list-reviews-for-a-pull-request)
和 [GraphQL PullRequestReview 字段](https://docs.github.com/en/graphql/reference/objects#pullrequestreview)构造；
本次未联网查阅文档，仍需在真实有评审的 PR 上核对。
ZIP 是测试生成的独立内容，测试只在内存中的产物副本替换 `digest`、`size_in_bytes`，
原始文件保持不变，真实下载摘要需由沙箱外的一致性检查核对。
