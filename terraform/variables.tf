variable "cloudflare_email" {
  type        = string
  description = "Cloudflare account email"
}

variable "cloudflare_api_key" {
  type        = string
  description = "Cloudflare Global API Key"
  sensitive   = true
}

variable "cloudflare_account_id" {
  type        = string
  description = "Cloudflare Account ID"
}

variable "cloudflare_zone_id" {
  type        = string
  description = "Optional Cloudflare Zone ID for custom domain routing (leave empty to use workers.dev)"
  default     = ""
}

variable "domain" {
  type        = string
  description = "Apex domain name for custom worker route (e.g. snowfox.live)"
  default     = "snowfox.live"
}

variable "subdomain" {
  type        = string
  description = "Subdomain prefix for worker route (e.g. routine)"
  default     = "routine"
}

variable "telegram_bot_token" {
  type        = string
  description = "Telegram Bot Token from BotFather"
  sensitive   = true
}

variable "routine_state_url" {
  type        = string
  description = "URL to the raw JSON state file in GitHub"
  default     = "https://raw.githubusercontent.com/snowfox-rubait/MIUroutine/main/state/batch71.json"
}
