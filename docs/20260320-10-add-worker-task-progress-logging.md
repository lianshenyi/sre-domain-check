# Worker 任务增加进度日志与容错处理

## 问题

Worker 执行 `update_all_domain_cert_info_of_user` 时，`kubectl logs` 只能看到任务开始和结束，中间没有任何输出：

```
10:09:23 domain-admin: ...execute_async_task(...)
10:11:07 domain-admin: Job OK (...)
```

导致两个问题：

1. 无法判断任务是"卡住了"还是"正在处理"
2. 部分域名没有更新，但不知道是哪些失败了、失败原因是什么

### 根因

- `update_all_domain_cert_info_of_user` 循环中没有 `try/except`，某个域名处理异常会导致整个循环中断，后续域名全部跳过
- 各层函数（`update_domain_row`、`update_domain_host_list`、`update_domain_address_list_cert`）没有 print 输出，RQ worker 的 stdout 不会显示任何进度信息
- `update_domain_host_list` 中 DNS 解析失败只写 logger（文件日志），不输出到 stdout

## 修复方案

### 1. `update_all_domain_cert_info_of_user` — 容错 + 进度汇总

- 循环内加 `try/except`，单个域名失败不影响后续域名
- 每个域名处理前 print 进度 `[1/50] domain=xxx`
- 循环结束后 print 汇总：总数、成功数、失败数、失败域名列表

### 2. `update_domain_row` — 入口日志

- 处理开始时 print 域名、ID、端口

### 3. `update_domain_host_list` — DNS 结果日志

- DNS 解析成功时 print 解析到的 IP 列表
- DNS 解析失败时 print 错误信息

### 4. `update_domain_address_list_cert` — 证书更新日志

- print 该域名下的地址数量
- 单个地址更新失败时 print 错误的 host 和原因

## 涉及文件

- `domain_admin/service/domain_service.py`

## 部署

需要重新构建 worker 镜像。

部署后 `kubectl logs` 输出示例：

```
[update_all] [1/50] domain=example.com id=1
[update_domain_row] start domain=example.com id=1 port=443
[update_host] domain=example.com hosts=['1.2.3.4', '5.6.7.8']
[update_cert] domain=example.com address_count=2
[update_all] [2/50] domain=test.com id=2
[update_domain_row] start domain=test.com id=2 port=443
[update_host] domain=test.com DNS resolve failed: [Errno -2] Name or service not known
[update_host] domain=test.com no hosts resolved
[update_cert] domain=test.com address_count=0
...
[update_all] done: user_id=1, total=50, success=48, fail=2, failed_domains=['bad1.com', 'bad2.com']
```
