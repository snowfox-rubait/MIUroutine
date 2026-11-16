output "worker_url" {
  description = "Public URL of the deployed Cloudflare Worker"
  value       = var.cloudflare_zone_id != "" ? "https://${var.subdomain}.${var.domain}" : "Deploy with custom zone or enable workers.dev route"
}

output "webhook_setup_url" {
  description = "Visit this URL in a browser to register the Telegram webhook with Cloudflare"
  value       = var.cloudflare_zone_id != "" ? "https://${var.subdomain}.${var.domain}/setup-webhook" : "Deploy with custom zone or enable workers.dev route"
}
