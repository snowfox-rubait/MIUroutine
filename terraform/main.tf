resource "cloudflare_worker_script" "bot_worker" {
  account_id = var.cloudflare_account_id
  name       = "miuroutine-bot"
  content    = file("${path.module}/../worker/worker.js")
  module     = true

  secret_text_binding {
    name = "TELEGRAM_BOT_TOKEN"
    text = var.telegram_bot_token
  }

  plain_text_binding {
    name = "ROUTINE_STATE_URL"
    text = var.routine_state_url
  }
}

resource "cloudflare_record" "worker_dns" {
  count   = var.cloudflare_zone_id != "" ? 1 : 0
  zone_id = var.cloudflare_zone_id
  name    = var.subdomain
  value   = "100::"
  type    = "AAAA"
  proxied = true
}

resource "cloudflare_worker_route" "worker_route" {
  count       = var.cloudflare_zone_id != "" ? 1 : 0
  zone_id     = var.cloudflare_zone_id
  pattern     = "${var.subdomain}.${var.domain}/*"
  script_name = cloudflare_worker_script.bot_worker.name
  depends_on  = [cloudflare_record.worker_dns]
}
