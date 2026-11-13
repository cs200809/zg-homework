# 本地部署和打包

从仓库根目录执行：

```sh
zg-homework-server/scripts/deploy_local.sh start  # start、stop、statu、status、restart
zg-homework-web/scripts/deploy_local.sh start     # start、stop、statu、status、restart
zg-homework-docs/scripts/package_all.sh --dev  # 或 --prod
```

脚本使用当前工作区的代码，包含未提交的修改，不会执行 Git 拉取。部署前按配置文件填写端口、数据库、JWT 和前端来源；生产配置位于 `zg-homework-docs/config-prod/`。前端 `server.domain` 支持带协议的地址；未指定协议时使用 HTTP。修改前端端口或域名时，请同步更新服务端 `cors.origins`。

本地服务端部署需要 Python 3.12，首次运行会在服务端目录创建 `.venv` 并安装 `requirements.txt` 中的依赖；依赖版本变化时也会更新。前端需要 Node.js 20 以上和已安装的 npm 依赖。脚本不会停止占用端口的进程，启动日志位于 `.dev-logs/`。

省略操作时默认为 `start`。`statu` 和 `status` 均查询状态；`restart` 先停止脚本管理的进程，再重新构建并启动。进程记录保存在 `.dev-logs/`，以前由旧脚本启动的进程不受管理，需先自行停止。

打包输出到 `zg-homework-tests/tar/`。压缩包包含数据库密码和 JWT 密钥，请限制访问。解压后，在 `zg-homework-server` 目录运行 `./install_server.sh` 检查环境和配置，运行 `./deploy_server.sh` 检查并启动服务；两者均不安装依赖。前端包包含源码和生成的 `.env.production`，可安装依赖后执行 `npm run build`。生产环境运行前应替换开发用的数据库凭据和密钥，并配置正确的 CORS 来源。
