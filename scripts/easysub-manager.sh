#!/usr/bin/env bash
# EasySub server manager. It only replaces the application container; it never removes data.

set -uo pipefail

APP_NAME="${EASYSUB_CONTAINER:-easysub}"
DB_NAME="${EASYSUB_DB_CONTAINER:-easysub-db}"
APP_DIR="${EASYSUB_DIR:-$HOME/easysub-custom}"
BRANCH="${EASYSUB_BRANCH:-main}"
BACKUP_DIR="${EASYSUB_BACKUP_DIR:-$HOME/easysub-backups}"
ENV_FILE="${EASYSUB_ENV_FILE:-$HOME/.config/easysub/container.env}"

IMAGE=""
DATA_SOURCE=""
DATA_TYPE=""
DATA_VOLUME_SPEC=""
RESTART_POLICY="unless-stopped"
declare -a NETWORKS=()
declare -a PORT_LINES=()

say() { printf '%s\n' "$*"; }
fail() { say "错误：$*" >&2; return 1; }
pause() { read -r -p "按 Enter 返回菜单..." _; }

require_docker() {
  command -v docker >/dev/null 2>&1 || fail "未找到 Docker 命令。"
  docker info >/dev/null 2>&1 || fail "无法连接 Docker，请使用有 Docker 权限的账户执行。"
}

container_exists() {
  docker container inspect "$1" >/dev/null 2>&1
}

discover_container() {
  if ! container_exists "$APP_NAME"; then
    fail "未找到应用容器：$APP_NAME"
    return 1
  fi

  IMAGE="$(docker inspect -f '{{.Config.Image}}' "$APP_NAME")" || return 1
  RESTART_POLICY="$(docker inspect -f '{{.HostConfig.RestartPolicy.Name}}' "$APP_NAME")" || return 1
  [[ -n "$RESTART_POLICY" && "$RESTART_POLICY" != "no" ]] || RESTART_POLICY="unless-stopped"

  local mount data_name data_host_path
  mount="$(docker inspect -f '{{range .Mounts}}{{if eq .Destination "/app/data"}}{{printf "%s\t%s\t%s" .Type .Name .Source}}{{end}}{{end}}' "$APP_NAME")" || return 1
  if [[ -z "$mount" ]]; then
    fail "容器没有挂载 /app/data，已停止操作以避免图标和数据库配置丢失。"
    return 1
  fi
  IFS=$'\t' read -r DATA_TYPE data_name data_host_path <<< "$mount"
  if [[ "$DATA_TYPE" == "volume" && -n "$data_name" ]]; then
    DATA_SOURCE="$data_name"
    DATA_VOLUME_SPEC="$data_name:/app/data"
  elif [[ "$DATA_TYPE" == "bind" && -n "$data_host_path" ]]; then
    DATA_SOURCE="$data_host_path"
    DATA_VOLUME_SPEC="$data_host_path:/app/data"
  else
    fail "无法识别 /app/data 的持久化卷。"
    return 1
  fi

  mapfile -t NETWORKS < <(docker inspect -f '{{range $key, $_ := .NetworkSettings.Networks}}{{println $key}}{{end}}' "$APP_NAME")
  mapfile -t PORT_LINES < <(docker inspect -f '{{range $port, $bindings := .HostConfig.PortBindings}}{{range $bindings}}{{printf "%s\t%s\t%s\n" $port .HostIp .HostPort}}{{end}}{{end}}' "$APP_NAME")

  mkdir -p "$(dirname "$ENV_FILE")" || return 1
  docker inspect -f '{{range .Config.Env}}{{println .}}{{end}}' "$APP_NAME" > "$ENV_FILE" || return 1
  chmod 600 "$ENV_FILE"
}

show_status() {
  require_docker || return
  say ""
  say "EasySub 状态"
  say "========================================"
  if container_exists "$APP_NAME"; then
    discover_container || return
    docker ps -a --filter "name=^/${APP_NAME}$" --format '容器：{{.Names}}  状态：{{.Status}}  镜像：{{.Image}}'
    say "数据挂载：$DATA_TYPE:$DATA_SOURCE -> /app/data"
    say "网络：${NETWORKS[*]:-默认 bridge}"
    if ((${#PORT_LINES[@]})); then
      say "端口映射："
      printf '  %s\n' "${PORT_LINES[@]}"
    else
      say "端口映射：未直接发布（可能由反向代理访问）"
    fi
  else
    say "应用容器 $APP_NAME 不存在。"
  fi
  if container_exists "$DB_NAME"; then
    docker ps -a --filter "name=^/${DB_NAME}$" --format '数据库容器：{{.Names}}  状态：{{.Status}}'
  else
    say "数据库容器：未发现 $DB_NAME（可能是外部 MySQL）。"
  fi
  if [[ -d "$APP_DIR/.git" ]]; then
    say "源码：$APP_DIR ($(git -C "$APP_DIR" rev-parse --short HEAD 2>/dev/null || true))"
  else
    say "源码：$APP_DIR（未发现 Git 仓库）"
  fi
}

backup_data() {
  require_docker || return
  discover_container || return
  mkdir -p "$BACKUP_DIR" || return
  local stamp app_backup db_backup
  stamp="$(date +%Y%m%d-%H%M%S)"
  app_backup="$BACKUP_DIR/easysub-app-data-$stamp.tar.gz"
  db_backup="$BACKUP_DIR/easysub-mysql-$stamp.sql"

  say "正在备份 /app/data 到：$app_backup"
  docker run --rm -v "$DATA_SOURCE:/data:ro" -v "$BACKUP_DIR:/backup" alpine:3.20 \
    tar -czf "/backup/$(basename "$app_backup")" -C /data . || return 1
  say "应用数据备份完成。"

  if container_exists "$DB_NAME" && [[ "$(docker inspect -f '{{.State.Running}}' "$DB_NAME")" == "true" ]]; then
    say "正在备份 MySQL 容器 $DB_NAME 到：$db_backup"
    if docker exec "$DB_NAME" sh -c 'exec mysqldump -uroot -p"$MYSQL_ROOT_PASSWORD" --all-databases --single-transaction' > "$db_backup.partial"; then
      mv "$db_backup.partial" "$db_backup"
      say "MySQL 备份完成。"
    else
      rm -f "$db_backup.partial"
      say "MySQL 备份失败；应用数据备份仍已保留。"
      return 1
    fi
  else
    say "未发现正在运行的 $DB_NAME。若你使用外部 MySQL，请按该数据库服务商的方式单独备份。"
  fi
  say "备份目录：$BACKUP_DIR"
}

wait_for_health() {
  local i
  for i in $(seq 1 20); do
    if docker exec "$APP_NAME" python -c "import json, urllib.request; data=json.load(urllib.request.urlopen('http://127.0.0.1:8000/api/health', timeout=2)); assert data.get('status') == 'ok'" >/dev/null 2>&1; then
      return 0
    fi
    sleep 2
  done
  return 1
}

restore_old_container() {
  local old_name="$1"
  say "新容器未能通过健康检查，正在自动恢复旧容器..."
  docker rm -f "$APP_NAME" >/dev/null 2>&1 || true
  docker rename "$old_name" "$APP_NAME" || return 1
  docker start "$APP_NAME" || return 1
  say "已恢复旧容器。请执行“查看应用日志”定位问题。"
}

start_replacement() {
  local new_image="$1"
  local old_name="$2"
  local -a args=(run -d --name "$APP_NAME" --env-file "$ENV_FILE" --restart "$RESTART_POLICY")
  local line container_port host_ip host_port

  args+=(-v "$DATA_VOLUME_SPEC")
  for line in "${PORT_LINES[@]}"; do
    IFS=$'\t' read -r container_port host_ip host_port <<< "$line"
    container_port="${container_port%/*}"
    if [[ -z "$host_ip" || "$host_ip" == "0.0.0.0" ]]; then
      args+=(-p "$host_port:$container_port")
    elif [[ "$host_ip" == "::" ]]; then
      args+=(-p "[$host_ip]:$host_port:$container_port")
    else
      args+=(-p "$host_ip:$host_port:$container_port")
    fi
  done
  if ((${#NETWORKS[@]})); then
    args+=(--network "${NETWORKS[0]}")
  fi

  docker "${args[@]}" "$new_image" >/dev/null || return 1
  local network
  for network in "${NETWORKS[@]:1}"; do
    docker network connect "$network" "$APP_NAME" || return 1
  done
  wait_for_health
}

update_application() {
  require_docker || return
  if [[ ! -d "$APP_DIR/.git" ]]; then
    fail "源码目录不是 Git 仓库：$APP_DIR"
    return 1
  fi
  if ! container_exists "$APP_NAME"; then
    fail "未找到应用容器 $APP_NAME，无法安全保留现有部署参数。"
    return 1
  fi
  if [[ -n "$(git -C "$APP_DIR" status --porcelain)" ]]; then
    fail "源码目录有未提交的修改。请先提交或还原这些修改，再执行更新。"
    return
  fi

  say "将从 origin/$BRANCH 拉取代码并重新构建镜像。"
  read -r -p "继续吗？[y/N] " answer
  [[ "${answer,,}" == "y" || "${answer,,}" == "yes" ]] || return

  git -C "$APP_DIR" pull --ff-only origin "$BRANCH" || return
  local stamp new_image old_name
  stamp="$(date +%Y%m%d-%H%M%S)"
  new_image="easysub-custom:$stamp"
  old_name="easysub-rollback-$stamp"
  say "正在构建镜像：$new_image"
  docker build -t "$new_image" "$APP_DIR" || return

  discover_container || return
  say "正在替换应用容器（MySQL 与 /app/data 不会被删除）..."
  docker stop "$APP_NAME" >/dev/null || return
  docker rename "$APP_NAME" "$old_name" || return
  if ! start_replacement "$new_image" "$old_name"; then
    restore_old_container "$old_name"
    return 1
  fi
  say "更新成功。旧容器保留为 $old_name，可在菜单中一键回滚。"
}

restart_application() {
  require_docker || return
  if ! container_exists "$APP_NAME"; then
    fail "未找到应用容器：$APP_NAME"
    return 1
  fi
  docker restart "$APP_NAME"
  if wait_for_health; then
    say "应用已重启并通过健康检查。"
  else
    say "应用已重启，但未通过健康检查。请查看日志。"
    return 1
  fi
}

rollback_application() {
  require_docker || return
  local old_name stamp replaced_name
  old_name="$(docker ps -a --format '{{.Names}}' | grep "^${APP_NAME}-rollback-" | sort | tail -n 1 || true)"
  if [[ -z "$old_name" ]]; then
    fail "没有可回滚的旧应用容器。"
    return 1
  fi
  stamp="$(date +%Y%m%d-%H%M%S)"
  replaced_name="${APP_NAME}-replaced-$stamp"
  read -r -p "将回滚到 $old_name，继续吗？[y/N] " answer
  [[ "${answer,,}" == "y" || "${answer,,}" == "yes" ]] || return

  docker stop "$APP_NAME" >/dev/null || return
  docker rename "$APP_NAME" "$replaced_name" || return
  if docker rename "$old_name" "$APP_NAME" && docker start "$APP_NAME" && wait_for_health; then
    say "回滚成功。刚才的版本保留为 $replaced_name。"
  else
    say "回滚启动失败，正在恢复刚才的版本..."
    docker rm -f "$APP_NAME" >/dev/null 2>&1 || true
    docker rename "$replaced_name" "$APP_NAME" >/dev/null 2>&1 || true
    docker start "$APP_NAME" >/dev/null 2>&1 || true
    return 1
  fi
}

view_logs() {
  require_docker || return
  if ! container_exists "$APP_NAME"; then
    fail "未找到应用容器：$APP_NAME"
    return 1
  fi
  say "显示最近 200 行日志。按 Ctrl+C 返回菜单。"
  docker logs --tail 200 -f "$APP_NAME"
}

menu() {
  say ""
  say "========================================"
  say "           EasySub 管理面板"
  say "========================================"
  say "应用容器：$APP_NAME    源码目录：$APP_DIR"
  say "1. 查看运行状态"
  say "2. 备份 MySQL 与应用数据"
  say "3. 拉取最新代码并重建应用"
  say "4. 查看应用日志"
  say "5. 重启应用"
  say "6. 回滚到上一个应用版本"
  say "0. 退出"
  say "----------------------------------------"
}

main() {
  require_docker || exit 1
  while true; do
    menu
    read -r -p "请选择 [0-6]: " choice
    case "$choice" in
      1) show_status; pause ;;
      2) backup_data; pause ;;
      3) update_application; pause ;;
      4) view_logs; pause ;;
      5) restart_application; pause ;;
      6) rollback_application; pause ;;
      0) exit 0 ;;
      *) say "请输入 0 到 6。" ;;
    esac
  done
}

main "$@"
