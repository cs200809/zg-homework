# 配置项
## mysql 数据库配置
### dev
```
    url: jdbc:mysql://localhost:3306/zg_homework?useUnicode=true&characterEncoding=utf8&useSSL=false&serverTimezone=Asia/Shanghai&allowPublicKeyRetrieval=true
    username: root
    password: GaGa@12345678
```
### prod
``` 
    url: jdbc:mysql://127.0.0.1:3306/homework_points?useUnicode=true&characterEncoding=utf8&useSSL=false&serverTimezone=Asia/Shanghai&allowPublicKeyRetrieval=true
    username: homework_user
    password: GaGaHp@12345678
```
## admin 账号

- 用户名：`admin`
- 密码：`12345678`

> 种子初始化时若未设置 `ADMIN_INIT_PASSWORD`，admin 密码会随机生成且**仅打印一次**，
> 首登改密后即失效。忘记密码时用重置命令改回：
>
> ```bash
> cd zg-homework-server
> python -m app.utils.reset_password admin --password 'admin123456'
> ```
>
> 省略 `--password` 则随机生成并打印。

