/**
 * MIU Routine Telegram Webhook Worker
 * Cloudflare Worker providing interactive bot capabilities:
 * - Inline buttons with ephemeral "show_alert: true" popups (zero group clutter)
 * - /today, /tomorrow, /week, /routine commands
 * - Direct PM responses
 */

const BANGLADESH_OFFSET_HOURS = 6;

function getDhakaDate() {
  const now = new Date();
  const utc = now.getTime() + now.getTimezoneOffset() * 60000;
  return new Date(utc + 3600000 * BANGLADESH_OFFSET_HOURS);
}

function getDayName(offsetDays = 0) {
  const d = getDhakaDate();
  if (offsetDays !== 0) {
    d.setDate(d.getDate() + offsetDays);
  }
  const days = ["Sunday", "Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday"];
  return days[d.getDay()];
}

function fmtTime(minutes) {
  const h = Math.floor(minutes / 60);
  const m = minutes % 60;
  const ap = h < 12 ? "AM" : "PM";
  const hh = h % 12 || 12;
  const mm = m < 10 ? `0${m}` : m;
  return `${hh}:${mm} ${ap}`;
}

function fmtRange(start, end) {
  return `${fmtTime(start)}–${fmtTime(end)}`;
}

async function getSchedule(env) {
  const defaultUrl = "https://raw.githubusercontent.com/snowfox-rubait/MIUroutine/main/state/batch71.json";
  const url = env.ROUTINE_STATE_URL || defaultUrl;

  try {
    const res = await fetch(url, {
      cf: { cacheTtl: 180, cacheEverything: true },
    });
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    return await res.json();
  } catch (err) {
    console.error("Failed to load schedule state:", err);
    return null;
  }
}

function formatDaySessions(sessions, dayName) {
  const dayClasses = (sessions || []).filter((s) => s.day === dayName);
  if (!dayClasses.length) {
    return `🎉 No classes scheduled for ${dayName}! Enjoy your day.`;
  }

  let text = `📅 Classes for ${dayName}:\n\n`;
  for (const s of dayClasses) {
    text += `• ${fmtRange(s.start, s.end)}\n  ${s.title} (${s.code})\n  Room: ${s.room} · ${s.teacher}\n\n`;
  }
  return text.trim();
}

function formatWeekSchedule(sessions, updatedOn) {
  if (!sessions || !sessions.length) {
    return "Schedule information is currently unavailable.";
  }

  const daysOrder = ["Sunday", "Monday", "Tuesday", "Wednesday", "Thursday", "Saturday"];
  let text = "📋 Weekly Routine (Batch 71)\n";
  if (updatedOn) text += `Updated on: ${updatedOn}\n`;
  text += "───────────────\n\n";

  let foundAny = false;
  for (const day of daysOrder) {
    const dayClasses = sessions.filter((s) => s.day === day);
    if (dayClasses.length) {
      foundAny = true;
      text += `【 ${day} 】\n`;
      for (const s of dayClasses) {
        text += `• ${fmtRange(s.start, s.end)}: ${s.code} (${s.room})\n`;
      }
      text += "\n";
    }
  }

  return foundAny ? text.trim() : "No active sessions found.";
}

function formatCoursesList(sessions) {
  const map = new Map();
  for (const s of sessions || []) {
    if (!map.has(s.code)) {
      map.set(s.code, { title: s.title, teacher: s.teacher });
    }
  }
  let text = "📚 Courses & Faculty (Batch 71):\n\n";
  for (const [code, info] of map.entries()) {
    text += `• ${code}: ${info.title}\n  Faculty: ${info.teacher}\n\n`;
  }
  return text.trim();
}

async function tgApi(env, method, payload) {
  const url = `https://api.telegram.org/bot${env.TELEGRAM_BOT_TOKEN}/${method}`;
  const res = await fetch(url, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  return await res.json();
}

export default {
  async fetch(request, env) {
    const url = new URL(request.url);

    // Health check
    if (url.pathname === "/" || url.pathname === "/health") {
      return new Response(JSON.stringify({ status: "ok", service: "MIU Routine Worker" }), {
        headers: { "Content-Type": "application/json" },
      });
    }

    // Webhook setup helper: GET /setup-webhook?secret=...
    if (url.pathname === "/setup-webhook") {
      const webhookUrl = `${url.origin}/webhook`;
      const res = await tgApi(env, "setWebhook", {
        url: webhookUrl,
        allowed_updates: ["message", "callback_query"],
      });
      return new Response(JSON.stringify(res, null, 2), {
        headers: { "Content-Type": "application/json" },
      });
    }

    // Telegram webhook receiver
    if (url.pathname === "/webhook" && request.method === "POST") {
      let update;
      try {
        update = await request.json();
      } catch {
        return new Response("Invalid JSON", { status: 400 });
      }

      const scheduleData = await getSchedule(env);
      const sessions = scheduleData?.sessions || [];
      const updatedOn = scheduleData?.sheet_updated_on || "";

      // 1. Handle Inline Button Clicks (Callback Query)
      if (update.callback_query) {
        const cb = update.callback_query;
        const action = cb.data;
        const isGroup = cb.message?.chat?.type === "group" || cb.message?.chat?.type === "supergroup";

        let popupText = "";
        if (action === "today") {
          popupText = formatDaySessions(sessions, getDayName(0));
        } else if (action === "tomorrow") {
          popupText = formatDaySessions(sessions, getDayName(1));
        } else if (action === "week") {
          popupText = formatWeekSchedule(sessions, updatedOn);
        } else if (action === "courses") {
          popupText = formatCoursesList(sessions);
        } else {
          popupText = "Unknown action.";
        }

        // In a group, answer with show_alert: true for an ephemeral popup modal
        // visible only to that user!
        await tgApi(env, "answerCallbackQuery", {
          callback_query_id: cb.id,
          text: popupText,
          show_alert: true,
        });

        return new Response("OK");
      }

      // 2. Handle Text Messages & Slash Commands
      if (update.message && update.message.text) {
        const msg = update.message;
        const text = msg.text.trim().toLowerCase();
        const chatId = msg.chat.id;
        const isGroup = msg.chat.type === "group" || msg.chat.type === "supergroup";

        const botUsername = env.TELEGRAM_BOT_USERNAME || "miuroutinebot";

        // Menu / Start / Routine command
        if (
          text.startsWith("/start") ||
          text.startsWith("/routine") ||
          text.startsWith("/menu") ||
          text.startsWith("/help")
        ) {
          const keyboard = {
            inline_keyboard: [
              [
                { text: "📅 Today's Classes", callback_data: "today" },
                { text: "📆 Tomorrow", callback_data: "tomorrow" },
              ],
              [
                { text: "📋 Full Week Routine", callback_data: "week" },
                { text: "📚 Course Catalog", callback_data: "courses" },
              ],
              [
                { text: "💬 Open in Private DM", url: `https://t.me/${botUsername}?start=routine` },
              ],
            ],
          };

          const replyText =
            `🎓 <b>MIU Routine Assistant (Batch 71)</b>\n\n` +
            `Tap an option below to view class schedules.\n` +
            `<i>(In groups, buttons display private popups visible only to you)</i>`;

          await tgApi(env, "sendMessage", {
            chat_id: chatId,
            text: replyText,
            parse_mode: "HTML",
            reply_markup: keyboard,
          });

          return new Response("OK");
        }

        // /today command
        if (text.startsWith("/today")) {
          const todaySchedule = formatDaySessions(sessions, getDayName(0));
          if (isGroup) {
            // Give them button so they can tap to view without group spam
            const keyboard = {
              inline_keyboard: [[{ text: "👁️ View Today's Classes (Private)", callback_data: "today" }]],
            };
            await tgApi(env, "sendMessage", {
              chat_id: chatId,
              text: `📅 Click below to view today's schedule privately:`,
              reply_markup: keyboard,
            });
          } else {
            await tgApi(env, "sendMessage", {
              chat_id: chatId,
              text: todaySchedule,
            });
          }
          return new Response("OK");
        }

        // /tomorrow command
        if (text.startsWith("/tomorrow")) {
          const tomorrowSchedule = formatDaySessions(sessions, getDayName(1));
          if (isGroup) {
            const keyboard = {
              inline_keyboard: [[{ text: "👁️ View Tomorrow's Classes (Private)", callback_data: "tomorrow" }]],
            };
            await tgApi(env, "sendMessage", {
              chat_id: chatId,
              text: `📆 Click below to view tomorrow's schedule privately:`,
              reply_markup: keyboard,
            });
          } else {
            await tgApi(env, "sendMessage", {
              chat_id: chatId,
              text: tomorrowSchedule,
            });
          }
          return new Response("OK");
        }

        // /week command
        if (text.startsWith("/week")) {
          const weekSchedule = formatWeekSchedule(sessions, updatedOn);
          if (isGroup) {
            const keyboard = {
              inline_keyboard: [[{ text: "👁️ View Full Week (Private)", callback_data: "week" }]],
            };
            await tgApi(env, "sendMessage", {
              chat_id: chatId,
              text: `📋 Click below to view the full weekly schedule privately:`,
              reply_markup: keyboard,
            });
          } else {
            await tgApi(env, "sendMessage", {
              chat_id: chatId,
              text: weekSchedule,
            });
          }
          return new Response("OK");
        }
      }

      return new Response("Ignored", { status: 200 });
    }

    return new Response("Not Found", { status: 404 });
  },
};
