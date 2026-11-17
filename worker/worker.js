/**
 * MIU Routine Telegram Webhook Worker
 * Cloudflare Worker providing interactive bot capabilities:
 * - Inline buttons with ephemeral "show_alert: true" popups (zero group clutter)
 * - /today, /tomorrow, /week, /routine commands
 * - Direct PM responses with full HTML formatting
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
      cf: { cacheTtl: 120, cacheEverything: true },
    });
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    return await res.json();
  } catch (err) {
    console.error("Failed to load schedule state:", err);
    return null;
  }
}

// Concise format for Telegram Alert Modals (strictly under 200 chars)
function formatConciseDay(sessions, dayName) {
  const dayClasses = (sessions || []).filter((s) => s.day === dayName);
  if (!dayClasses.length) {
    return `🎉 No classes scheduled for ${dayName}! Enjoy your day.`;
  }

  let text = `📅 ${dayName} (${dayClasses.length} class${dayClasses.length > 1 ? "es" : ""}):\n`;
  for (const s of dayClasses) {
    text += `• ${fmtRange(s.start, s.end)}: ${s.code} (${s.room})\n`;
  }
  return text.trim();
}

// Full rich HTML format for chat messages & DMs
function formatDaySessions(sessions, dayName) {
  const dayClasses = (sessions || []).filter((s) => s.day === dayName);
  if (!dayClasses.length) {
    return `🎉 <b>No classes scheduled for ${dayName}!</b> Enjoy your day.`;
  }

  let text = `📅 <b>Classes for ${dayName}:</b>\n\n`;
  for (const s of dayClasses) {
    text += `• <b>${fmtRange(s.start, s.end)}</b>\n  ${s.title} (<code>${s.code}</code>)\n  📍 Room: <b>${s.room}</b> · 👨‍🏫 ${s.teacher}\n\n`;
  }
  return text.trim();
}

function formatWeekSchedule(sessions, updatedOn) {
  if (!sessions || !sessions.length) {
    return "Schedule information is currently unavailable.";
  }

  const daysOrder = ["Sunday", "Monday", "Tuesday", "Wednesday", "Thursday", "Saturday"];
  let text = `📋 <b>Weekly Routine (Batch 71)</b>\n`;
  if (updatedOn) text += `<i>Sheet updated on: ${updatedOn}</i>\n`;
  text += `───────────────────────\n\n`;

  let foundAny = false;
  for (const day of daysOrder) {
    const dayClasses = sessions.filter((s) => s.day === day);
    if (dayClasses.length) {
      foundAny = true;
      text += `<b>【 ${day} 】</b>\n`;
      for (const s of dayClasses) {
        text += `• ${fmtRange(s.start, s.end)} · <b>${s.code}</b> · ${s.room}\n   <i>${s.title} (${s.teacher})</i>\n`;
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
  let text = `📚 <b>Courses & Faculty (Batch 71):</b>\n\n`;
  for (const [code, info] of map.entries()) {
    text += `• <b>${code}</b>: ${info.title}\n  Faculty: <i>${info.teacher}</i>\n\n`;
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

    // Webhook & Commands setup helper: GET /setup-webhook
    if (url.pathname === "/setup-webhook") {
      const webhookUrl = `${url.origin}/webhook`;
      const webhookRes = await tgApi(env, "setWebhook", {
        url: webhookUrl,
        allowed_updates: ["message", "callback_query"],
      });

      // Register bot commands list in Telegram
      const commandsRes = await tgApi(env, "setMyCommands", {
        commands: [
          { command: "today", description: "View today's classes" },
          { command: "tomorrow", description: "View tomorrow's classes" },
          { command: "week", description: "View full weekly routine" },
          { command: "routine", description: "Open interactive routine menu" },
          { command: "menu", description: "Open interactive routine menu" },
          { command: "help", description: "Help and information" },
        ],
      });

      return new Response(JSON.stringify({ webhook: webhookRes, commands: commandsRes }, null, 2), {
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
        const chatId = cb.message?.chat?.id;
        const userId = cb.from?.id;
        const isGroup = cb.message?.chat?.type === "group" || cb.message?.chat?.type === "supergroup";

        let fullText = "";
        let alertText = "";

        if (action === "today") {
          fullText = formatDaySessions(sessions, getDayName(0));
          alertText = formatConciseDay(sessions, getDayName(0));
        } else if (action === "tomorrow") {
          fullText = formatDaySessions(sessions, getDayName(1));
          alertText = formatConciseDay(sessions, getDayName(1));
        } else if (action === "week") {
          fullText = formatWeekSchedule(sessions, updatedOn);
          alertText = "📋 Weekly schedule sent! Check your Private DM with @miuroutinebot for the full timetable.";
        } else if (action === "courses") {
          fullText = formatCoursesList(sessions);
          alertText = "📚 Course catalog sent! Check your Private DM with @miuroutinebot for faculty details.";
        } else {
          fullText = "Unknown action.";
          alertText = "Unknown action.";
        }

        if (isGroup) {
          // In a group, answer with show_alert: true for an ephemeral popup modal
          // Telegram requires alert text to be strictly <= 200 characters!
          const safeAlert = alertText.length > 195 ? alertText.slice(0, 192) + "..." : alertText;
          await tgApi(env, "answerCallbackQuery", {
            callback_query_id: cb.id,
            text: safeAlert,
            show_alert: true,
          });

          // For week and courses in group, also send detailed view to user's DM
          if (action === "week" || action === "courses") {
            try {
              await tgApi(env, "sendMessage", {
                chat_id: userId,
                text: fullText,
                parse_mode: "HTML",
              });
            } catch (e) {
              console.log("Could not DM user:", e);
            }
          }
        } else {
          // In Private DM: stop loading spinner and send the full rich message!
          await tgApi(env, "answerCallbackQuery", {
            callback_query_id: cb.id,
          });

          await tgApi(env, "sendMessage", {
            chat_id: chatId,
            text: fullText,
            parse_mode: "HTML",
          });
        }

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
                { text: "💬 Open in Private DM", url: `https://t.me/${botUsername}?start=menu` },
              ],
            ],
          };

          const replyText =
            `🎓 <b>MIU Routine Assistant (CSE Batch 71)</b>\n\n` +
            `Choose an option below to view class schedules.\n` +
            `<i>• In groups: buttons display private popups visible only to you.</i>\n` +
            `<i>• In private DM: sends the full detailed timetable.</i>`;

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
          await tgApi(env, "sendMessage", {
            chat_id: chatId,
            text: todaySchedule,
            parse_mode: "HTML",
          });
          return new Response("OK");
        }

        // /tomorrow command
        if (text.startsWith("/tomorrow")) {
          const tomorrowSchedule = formatDaySessions(sessions, getDayName(1));
          await tgApi(env, "sendMessage", {
            chat_id: chatId,
            text: tomorrowSchedule,
            parse_mode: "HTML",
          });
          return new Response("OK");
        }

        // /week command
        if (text.startsWith("/week")) {
          const weekSchedule = formatWeekSchedule(sessions, updatedOn);
          await tgApi(env, "sendMessage", {
            chat_id: chatId,
            text: weekSchedule,
            parse_mode: "HTML",
          });
          return new Response("OK");
        }
      }

      return new Response("Ignored", { status: 200 });
    }

    return new Response("Not Found", { status: 404 });
  },
};
