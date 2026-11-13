# 本地部署和打包

从仓库根目录执行：

```sh
zg-homework-server/scripts/deploy_local.sh start  # start、stop、statu、status、restart
zg-homework-web/scripts/deploy_local.sh start     # start、stop、statu、status、restart
zg-homework-docs/scripts/package_all.sh --dev  # 或 --prod
```

脚本使用当前工作区的代码，包含未提交和未跟踪的修改，不会切换分支或执行 Git 拉取；打包和部署前请自行确认当前分支、工作区内容和配置。项目发布约定是在 `feature/dev_deploy` 测试通过后合并到 `main`，从 `main` 打包和部署。

本地部署使用 `zg-homework-docs/config-dev/` 中的配置；`--dev` 和 `--prod` 分别读取 `config-dev/` 和 `config-prod/`。生产环境的 `config-prod/server-build.config` 当前为空，`web-build.config` 中的域名也是占位值，不能直接用于生产打包；请先填写完整且有效的端口、数据库、JWT、前端来源和真实域名，再执行 `--prod`。前端 `server.domain` 支持带协议的地址；未指定协议时使用 HTTP。修改前端端口或域名时，请同步更新服务端 `cors.origins`。

本地服务端部署需要 Python 3.12，首次运行会在服务端目录创建 `.venv` 并安装 `requirements.txt` 中的依赖；依赖版本变化时也会更新。前端需要 Node.js 20 以上和已安装的 npm 依赖。脚本不会停止占用端口的进程，启动日志位于 `.dev-logs/`。

省略操作时默认为 `start`。`statu` 和 `status` 均查询状态；如果脚本管理的进程已运行，`start` 会报错并提示使用 `restart`，不会重新加载配置或代码、也不会重新构建前端。需要应用修改时请执行对应的 `restart`：它先停止脚本管理的进程，再重新启动（前端会重新构建）。进程记录保存在 `.dev-logs/`，以前由旧脚本启动的进程不受管理，需先自行停止。

启动成功依据服务端健康接口或前端页面返回 HTTP 200；服务端健康检查不检查数据库连接，不能证明数据库可用或业务接口正常，请另行验证数据库和业务功能。

打包输出到 `zg-homework-tests/tar/`。生产部署不得从归档读取真实密码或密钥；应由部署者在包外安全管理，并在运行时单独注入环境变量 `DATABASE_URL` 和 `JWT_SECRET`，不应将实际数据库凭据或 JWT 密钥放进归档。

打包生成的服务端 `.env` 不含 `DATABASE_URL` 和 `JWT_SECRET`。解压后，执行 `install_server.sh` 和 `deploy_server.sh` 时都必须从外部环境提供这两个非空变量；数据库地址须以 `mysql+pymysql://` 开头，用户名或密码中的 URL 特殊字符需要百分号编码。请通过安全的环境变量注入方式提供真实值，避免写入仓库、归档或 shell 历史。当前打包配置仍要求填写数据库及 JWT 配置项，可使用非生产占位值。

生成的归档文件权限为 `0600`，包内服务端 `.env` 也为 `0600`。这些权限不能替代安全的存储、传输和访问控制：请限制归档、解压目录及备份的访问，不要提交或公开分发，使用完安全清理。归档可能包含工作区中的其他文件和敏感信息，打包前应自行检查；脚本排除部分目录和文件，但不是敏感信息扫描器或安全边界。

解压后，在 `zg-homework-server` 目录运行 `./install_server.sh` 检查环境和配置，运行 `./deploy_server.sh` 检查并启动服务；两者均不安装依赖，也不初始化数据库。前端包包含源码和生成的 `.env.production`，可安装依赖后执行 `npm run build`。生产环境运行前应替换开发用的数据库凭据和密钥，并配置正确的 CORS 来源。

## 与 systemd 生产部署的区别

这里的本地脚本以当前用户身份启动仅监听 `127.0.0.1` 的进程，前端使用 Vite preview；打包后的 `deploy_server.sh` 也只是直接启动服务，不注册 systemd 单元，不提供开机自启或进程托管，也不配置 nginx、TLS 或公网访问。它不是生产 systemd 部署的替代品。生产环境的 systemd + 共享 nginx 方案使用模块各自的 `server_package.sh`、`web_package.sh` 和 `install.sh` 等脚本，部署步骤、安全约束与产物不同；详见仓库根目录 `CLAUDE.md` 和 `zg-homework-docs/sys_doc/生产部署打包方案.md`。
