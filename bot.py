#!/usr/bin/env python3
# ============================================================
#   TELEGRAM MULTI-ACCOUNT ANNOUNCEMENT + VOTE BOT
#   Token & Admin: Pre-configured
#   Server: Railway.app ready
# ============================================================

import logging
import asyncio
from telegram import (
    Update,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
)
from telegram.ext import (
    Application,
    CommandHandler,
    CallbackQueryHandler,
    MessageHandler,
    ConversationHandler,
    filters,
    ContextTypes,
)
from telegram.constants import ParseMode
from config import BOT_TOKEN, ADMIN_IDS, SEND_DELAY
from database import Database

# ─── Logging ────────────────────────────────────────────────
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
    handlers=[
        logging.FileHandler("bot.log"),
        logging.StreamHandler(),
    ],
)
logger = logging.getLogger(__name__)

# ─── Conversation States ─────────────────────────────────────
(
    MAIN_MENU,
    ANNOUNCEMENT_TEXT,
    ANNOUNCEMENT_IMAGE,
    ANNOUNCEMENT_BUTTONS,
    ANNOUNCEMENT_SELECT_GROUPS,
    VOTE_QUESTION,
    VOTE_OPTIONS,
    VOTE_SELECT_GROUPS,
    CONFIRM_SEND,
    WAIT_IMAGE,
    ADD_BUTTON_TEXT,
) = range(11)

db = Database()


# ══════════════════════════════════════════════════════════════
#   HELPERS
# ══════════════════════════════════════════════════════════════

def is_admin(user_id: int) -> bool:
    return user_id in ADMIN_IDS


def main_menu_keyboard():
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("📢 Announcement", callback_data="menu_announce"),
            InlineKeyboardButton("🗳️ Vote / Poll", callback_data="menu_vote"),
        ],
        [
            InlineKeyboardButton("👥 My Groups", callback_data="menu_groups"),
            InlineKeyboardButton("📊 Statistics", callback_data="menu_stats"),
        ],
        [
            InlineKeyboardButton("❓ Help", callback_data="menu_help"),
        ],
    ])


def group_selection_keyboard(user_id: int, selected: list, page: int = 0):
    groups = db.get_user_groups(user_id)
    per_page = 6
    start = page * per_page
    end = start + per_page
    page_groups = groups[start:end]

    keyboard = []
    for group in page_groups:
        gid = str(group["group_id"])
        name = group["group_name"][:28]
        tick = "✅" if gid in selected else "☐"
        keyboard.append([
            InlineKeyboardButton(f"{tick} {name}", callback_data=f"toggle_{gid}")
        ])

    # Select All + Navigation row
    all_selected = len(selected) == len(groups) and len(groups) > 0
    nav = []
    if page > 0:
        nav.append(InlineKeyboardButton("◀️ Prev", callback_data=f"page_{page-1}"))
    nav.append(InlineKeyboardButton(
        "☑️ Deselect All" if all_selected else "✅ Select All",
        callback_data="select_all"
    ))
    if end < len(groups):
        nav.append(InlineKeyboardButton("Next ▶️", callback_data=f"page_{page+1}"))
    keyboard.append(nav)

    keyboard.append([
        InlineKeyboardButton("🔙 Back", callback_data="back_main"),
        InlineKeyboardButton(
            f"▶️ Next  ({len(selected)} selected)",
            callback_data="confirm_groups"
        ),
    ])
    return InlineKeyboardMarkup(keyboard), len(groups)


# ══════════════════════════════════════════════════════════════
#   START / MAIN MENU
# ══════════════════════════════════════════════════════════════

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    if not is_admin(user.id):
        await update.message.reply_text(
            "❌ *Unauthorized!*\n\nTum is bot ke admin nahi ho.",
            parse_mode=ParseMode.MARKDOWN,
        )
        return ConversationHandler.END

    db.register_user(user.id, user.username or user.first_name)
    context.user_data.clear()

    groups_count = len(db.get_user_groups(user.id))

    await update.message.reply_text(
        f"👋 *Welcome, {user.first_name}!*\n\n"
        f"🤖 *Multi-Group Announcement Bot*\n\n"
        f"👥 Tumhare registered groups: *{groups_count}*\n\n"
        f"📢 Announcement — sab groups mein message bhejo\n"
        f"🗳️ Vote/Poll — sabko poll bhejo\n"
        f"✅ Select All — ek tap mein sab select\n\n"
        f"_Niche se option choose karo:_",
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=main_menu_keyboard(),
    )
    return MAIN_MENU


# ══════════════════════════════════════════════════════════════
#   MAIN MENU CALLBACKS
# ══════════════════════════════════════════════════════════════

async def menu_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id

    # ── Back to Main ──
    if query.data == "back_main":
        context.user_data.clear()
        groups_count = len(db.get_user_groups(user_id))
        await query.edit_message_text(
            f"🏠 *Main Menu*\n\n👥 Groups: *{groups_count}*\n\nOption choose karo:",
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=main_menu_keyboard(),
        )
        return MAIN_MENU

    # ── Announcement ──
    elif query.data == "menu_announce":
        context.user_data["mode"] = "announce"
        context.user_data["announcement"] = {}
        await query.edit_message_text(
            "📢 *Announcement Type Choose Karo:*",
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("📝 Sirf Text", callback_data="ann_text")],
                [InlineKeyboardButton("🖼️ Image + Caption", callback_data="ann_image")],
                [InlineKeyboardButton("🔙 Back", callback_data="back_main")],
            ]),
        )
        return ANNOUNCEMENT_TEXT

    # ── Vote ──
    elif query.data == "menu_vote":
        context.user_data["mode"] = "vote"
        context.user_data["vote"] = {"options": []}
        await query.edit_message_text(
            "🗳️ *Vote / Poll Banao*\n\n"
            "Poll ka *question* bhejo:\n\n"
            "_Example: Aaj meeting kab karein?_",
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton("🔙 Cancel", callback_data="back_main")
            ]]),
        )
        return VOTE_QUESTION

    # ── My Groups ──
    elif query.data == "menu_groups":
        groups = db.get_user_groups(user_id)
        if not groups:
            text = (
                "👥 *Mere Groups*\n\n"
                "❌ Koi group nahi mila!\n\n"
                "*Kaise add karein:*\n"
                "1️⃣ Bot ko apne group mein add karo\n"
                "2️⃣ Bot ko *Admin* banao\n"
                "3️⃣ Group yahan automatically aayega ✅"
            )
        else:
            text = f"👥 *Mere Groups* — Total: *{len(groups)}*\n\n"
            for i, g in enumerate(groups, 1):
                text += f"`{i}.` {g['group_name']}\n"

        await query.edit_message_text(
            text,
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton("🔙 Back", callback_data="back_main")
            ]]),
        )
        return MAIN_MENU

    # ── Stats ──
    elif query.data == "menu_stats":
        stats = db.get_stats(user_id)
        await query.edit_message_text(
            "📊 *Tumhari Statistics*\n\n"
            f"👥 Total Groups: *{stats['groups']}*\n"
            f"📢 Announcements: *{stats['announcements']}*\n"
            f"🗳️ Polls: *{stats['polls']}*\n"
            f"✅ Delivered: *{stats['delivered']}*\n"
            f"❌ Failed: *{stats['failed']}*\n",
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton("🔙 Back", callback_data="back_main")
            ]]),
        )
        return MAIN_MENU

    # ── Help ──
    elif query.data == "menu_help":
        await query.edit_message_text(
            "❓ *Help*\n\n"
            "*Bot setup kaise karein:*\n"
            "1️⃣ Bot ko group mein add karo\n"
            "2️⃣ Bot ko Admin banao\n"
            "3️⃣ Automatically register hoga\n\n"
            "*Announcement kaise bhejein:*\n"
            "• 📢 Announcement tap karo\n"
            "• Text ya image choose karo\n"
            "• Message likho\n"
            "• Buttons add karo (optional)\n"
            "• Select All tap karo\n"
            "• Send! ✅\n\n"
            "*Multiple Accounts:*\n"
            "Har account ke groups alag hain.\n"
            "Mix nahi hoga kabhi! 🔒",
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton("🔙 Back", callback_data="back_main")
            ]]),
        )
        return MAIN_MENU

    return MAIN_MENU


# ══════════════════════════════════════════════════════════════
#   ANNOUNCEMENT FLOW
# ══════════════════════════════════════════════════════════════

async def announcement_type(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    if query.data == "ann_text":
        context.user_data["announcement"]["has_image"] = False
        await query.edit_message_text(
            "📝 *Announcement Text Likho:*\n\n"
            "Apna message type karke bhejo.\n\n"
            "_Formatting:_ *bold* `code` _italic_",
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton("🔙 Cancel", callback_data="back_main")
            ]]),
        )
        return ANNOUNCEMENT_TEXT

    elif query.data == "ann_image":
        context.user_data["announcement"]["has_image"] = True
        await query.edit_message_text(
            "🖼️ *Image Bhejo:*\n\nPhoto attach karke send karo.",
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton("🔙 Cancel", callback_data="back_main")
            ]]),
        )
        return WAIT_IMAGE

    return ANNOUNCEMENT_TEXT


async def receive_image(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message.photo:
        await update.message.reply_text("❌ Photo bhejo!")
        return WAIT_IMAGE

    context.user_data["announcement"]["photo_id"] = update.message.photo[-1].file_id

    await update.message.reply_text(
        "✅ Image mili!\n\n📝 *Ab caption/text bhejo:*\n_(ya skip karo)_",
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=InlineKeyboardMarkup([[
            InlineKeyboardButton("⏭️ Skip Caption", callback_data="skip_caption")
        ]]),
    )
    return ANNOUNCEMENT_TEXT


async def receive_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["announcement"]["text"] = update.message.text

    await update.message.reply_text(
        "✅ Text save hua!\n\n"
        "🔘 *Inline Button add karein?*\n\n"
        "_Example: Website link, Join channel button_",
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("➕ Button Add Karo", callback_data="add_button")],
            [InlineKeyboardButton("⏭️ Skip — Groups Select Karo", callback_data="goto_groups")],
            [InlineKeyboardButton("🔙 Cancel", callback_data="back_main")],
        ]),
    )
    return ANNOUNCEMENT_BUTTONS


async def skip_caption(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    context.user_data["announcement"]["text"] = ""

    await query.edit_message_text(
        "🔘 *Inline Button add karein?*",
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("➕ Button Add Karo", callback_data="add_button")],
            [InlineKeyboardButton("⏭️ Skip — Groups Select Karo", callback_data="goto_groups")],
        ]),
    )
    return ANNOUNCEMENT_BUTTONS


async def add_button_prompt(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    current = context.user_data["announcement"].get("buttons", [])
    count_text = f"(Abhi {len(current)} button hai)" if current else ""

    await query.edit_message_text(
        f"🔘 *Button Add Karo* {count_text}\n\n"
        "Is format mein bhejo:\n\n"
        "`Button Text | https://link.com`\n\n"
        "_Example:_\n`Join Channel | https://t.me/mychannel`\n"
        "`Website | https://mysite.com`",
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=InlineKeyboardMarkup([[
            InlineKeyboardButton("🔙 Back", callback_data="goto_groups")
        ]]),
    )
    return ADD_BUTTON_TEXT


async def receive_button(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text
    if "|" not in text:
        await update.message.reply_text(
            "❌ Format galat hai!\n\n"
            "Sahi format:\n`Button Text | https://link.com`",
            parse_mode=ParseMode.MARKDOWN,
        )
        return ADD_BUTTON_TEXT

    parts = text.split("|", 1)
    btn_text = parts[0].strip()
    btn_url = parts[1].strip()

    if not btn_url.startswith("http"):
        await update.message.reply_text("❌ URL `https://` se shuru hona chahiye!")
        return ADD_BUTTON_TEXT

    if "buttons" not in context.user_data["announcement"]:
        context.user_data["announcement"]["buttons"] = []

    context.user_data["announcement"]["buttons"].append({"text": btn_text, "url": btn_url})
    count = len(context.user_data["announcement"]["buttons"])

    await update.message.reply_text(
        f"✅ Button add hua: *{btn_text}*\n"
        f"Total buttons: *{count}*",
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("➕ Ek Aur Button", callback_data="add_button")],
            [InlineKeyboardButton(f"▶️ Groups Select Karo ({count} button)", callback_data="goto_groups")],
        ]),
    )
    return ANNOUNCEMENT_BUTTONS


async def goto_groups(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id

    context.user_data["selected_groups"] = []
    context.user_data["page"] = 0

    keyboard, total = group_selection_keyboard(user_id, [], 0)

    if total == 0:
        await query.edit_message_text(
            "❌ *Koi group nahi mila!*\n\n"
            "Pehle bot ko apne groups mein add karo aur Admin banao.",
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton("🔙 Main Menu", callback_data="back_main")
            ]]),
        )
        return MAIN_MENU

    await query.edit_message_text(
        f"👥 *Groups Select Karo*\n\n"
        f"Total groups: *{total}*\n"
        f"✅ Select All se sab ek saath select ho jaayenge!\n",
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=keyboard,
    )
    return ANNOUNCEMENT_SELECT_GROUPS


# ══════════════════════════════════════════════════════════════
#   GROUP SELECTION
# ══════════════════════════════════════════════════════════════

async def group_select_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id

    selected = context.user_data.get("selected_groups", [])
    page = context.user_data.get("page", 0)
    all_groups = db.get_user_groups(user_id)
    all_ids = [str(g["group_id"]) for g in all_groups]

    if query.data.startswith("toggle_"):
        gid = query.data.replace("toggle_", "")
        if gid in selected:
            selected.remove(gid)
        else:
            selected.append(gid)
        context.user_data["selected_groups"] = selected

    elif query.data == "select_all":
        if len(selected) == len(all_groups):
            context.user_data["selected_groups"] = []
        else:
            context.user_data["selected_groups"] = all_ids.copy()
        selected = context.user_data["selected_groups"]

    elif query.data.startswith("page_"):
        page = int(query.data.replace("page_", ""))
        context.user_data["page"] = page

    elif query.data == "confirm_groups":
        if not selected:
            await query.answer("⚠️ Kam se kam ek group select karo!", show_alert=True)
            return ANNOUNCEMENT_SELECT_GROUPS

        # Build preview
        selected_names = []
        for gid in selected:
            for g in all_groups:
                if str(g["group_id"]) == gid:
                    selected_names.append(g["group_name"])

        groups_preview = "\n".join([f"• {n}" for n in selected_names[:8]])
        if len(selected_names) > 8:
            groups_preview += f"\n_...aur {len(selected_names) - 8} groups_"

        mode = context.user_data.get("mode", "announce")
        ann = context.user_data.get("announcement", {})
        vote = context.user_data.get("vote", {})

        if mode == "announce":
            preview_text = ann.get("text", "_(No text)_")[:100]
            has_image = "🖼️ Image: Haan\n" if ann.get("photo_id") else ""
            has_buttons = f"🔘 Buttons: {len(ann.get('buttons', []))}\n" if ann.get("buttons") else ""
            content_preview = f"{has_image}{has_buttons}📝 Text: {preview_text}"
        else:
            content_preview = f"🗳️ Poll: {vote.get('question', '')}\n📊 Options: {len(vote.get('options', []))}"

        await query.edit_message_text(
            f"📋 *Confirm & Send*\n\n"
            f"{content_preview}\n\n"
            f"👥 *Send to {len(selected)} groups:*\n{groups_preview}\n\n"
            f"Ready hai?",
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=InlineKeyboardMarkup([
                [
                    InlineKeyboardButton("🚀 Send Now!", callback_data="send_now"),
                    InlineKeyboardButton("🔙 Back", callback_data="back_groups"),
                ]
            ]),
        )
        return CONFIRM_SEND

    keyboard, total = group_selection_keyboard(user_id, selected, page)
    try:
        await query.edit_message_text(
            f"👥 *Groups Select Karo*\n"
            f"Total: *{total}* | Selected: *{len(selected)}*\n\n"
            f"_✅ Select All se sab ek saath select karein_",
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=keyboard,
        )
    except Exception:
        pass
    return ANNOUNCEMENT_SELECT_GROUPS


# ══════════════════════════════════════════════════════════════
#   CONFIRM & SEND
# ══════════════════════════════════════════════════════════════

async def confirm_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id

    if query.data == "back_groups":
        selected = context.user_data.get("selected_groups", [])
        page = context.user_data.get("page", 0)
        keyboard, total = group_selection_keyboard(user_id, selected, page)
        await query.edit_message_text(
            f"👥 *Groups Select Karo*\nSelected: *{len(selected)}*",
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=keyboard,
        )
        return ANNOUNCEMENT_SELECT_GROUPS

    if query.data == "send_now":
        selected = context.user_data.get("selected_groups", [])
        mode = context.user_data.get("mode", "announce")

        await query.edit_message_text(
            f"⏳ *Sending...*\n\n"
            f"📤 {len(selected)} groups mein bhej raha hoon...\n"
            f"_Please wait..._",
            parse_mode=ParseMode.MARKDOWN,
        )

        success = 0
        failed = 0
        failed_list = []
        all_groups = db.get_user_groups(user_id)

        for gid in selected:
            gname = next((g["group_name"] for g in all_groups if str(g["group_id"]) == gid), gid)
            try:
                if mode == "announce":
                    await _send_announcement(context, int(gid), context.user_data.get("announcement", {}))
                else:
                    await _send_vote(context, int(gid), context.user_data.get("vote", {}))
                success += 1
            except Exception as e:
                failed += 1
                failed_list.append(gname)
                logger.error(f"Failed {gid} ({gname}): {e}")
            await asyncio.sleep(SEND_DELAY)

        db.update_stats(user_id, mode, success, failed)

        result = (
            f"✅ *Sending Complete!*\n\n"
            f"✅ Success: *{success}* groups\n"
            f"❌ Failed: *{failed}* groups\n"
        )
        if failed_list:
            result += "\n*Failed:*\n" + "\n".join([f"• {g}" for g in failed_list[:5]])

        await query.edit_message_text(
            result,
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton("🏠 Main Menu", callback_data="back_main")
            ]]),
        )
        context.user_data.clear()
        return MAIN_MENU

    return CONFIRM_SEND


async def _send_announcement(context, group_id: int, ann: dict):
    text = ann.get("text", "")
    photo_id = ann.get("photo_id")
    buttons = ann.get("buttons", [])

    reply_markup = None
    if buttons:
        reply_markup = InlineKeyboardMarkup([
            [InlineKeyboardButton(b["text"], url=b["url"])] for b in buttons
        ])

    if photo_id:
        await context.bot.send_photo(
            chat_id=group_id,
            photo=photo_id,
            caption=text or None,
            parse_mode=ParseMode.MARKDOWN if text else None,
            reply_markup=reply_markup,
        )
    else:
        await context.bot.send_message(
            chat_id=group_id,
            text=text,
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=reply_markup,
        )


async def _send_vote(context, group_id: int, vote: dict):
    options = vote.get("options", ["Yes", "No"])
    await context.bot.send_poll(
        chat_id=group_id,
        question=vote.get("question", "Vote karo:"),
        options=options,
        is_anonymous=vote.get("anonymous", True),
        allows_multiple_answers=vote.get("multiple", False),
    )


# ══════════════════════════════════════════════════════════════
#   VOTE FLOW
# ══════════════════════════════════════════════════════════════

async def receive_vote_question(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["vote"]["question"] = update.message.text
    await update.message.reply_text(
        f"✅ Question: *{update.message.text}*\n\n"
        "📝 *Ab options bhejo — ek ek karke:*\n\n"
        "_Minimum 2, Maximum 10 options_",
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=InlineKeyboardMarkup([[
            InlineKeyboardButton("✅ Done — Groups Choose Karo", callback_data="vote_done"),
            InlineKeyboardButton("🔙 Cancel", callback_data="back_main"),
        ]]),
    )
    return VOTE_OPTIONS


async def receive_vote_option(update: Update, context: ContextTypes.DEFAULT_TYPE):
    options = context.user_data["vote"].get("options", [])
    if len(options) >= 10:
        await update.message.reply_text("❌ Max 10 options!")
        return VOTE_OPTIONS

    options.append(update.message.text)
    context.user_data["vote"]["options"] = options
    opts_text = "\n".join([f"{i+1}. {o}" for i, o in enumerate(options)])

    await update.message.reply_text(
        f"✅ Option add hua!\n\n*Options:*\n{opts_text}",
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=InlineKeyboardMarkup([[
            InlineKeyboardButton(f"✅ Done ({len(options)} options)", callback_data="vote_done"),
            InlineKeyboardButton("🔙 Cancel", callback_data="back_main"),
        ]]),
    )
    return VOTE_OPTIONS


async def vote_done(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id

    if len(context.user_data["vote"].get("options", [])) < 2:
        await query.answer("⚠️ Kam se kam 2 options chahiye!", show_alert=True)
        return VOTE_OPTIONS

    context.user_data["vote"]["anonymous"] = True
    context.user_data["vote"]["multiple"] = False
    context.user_data["selected_groups"] = []
    context.user_data["page"] = 0

    keyboard, total = group_selection_keyboard(user_id, [], 0)

    if total == 0:
        await query.edit_message_text(
            "❌ Koi group nahi mila!",
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton("🔙 Back", callback_data="back_main")
            ]]),
        )
        return MAIN_MENU

    await query.edit_message_text(
        f"👥 *Groups Select Karo* (Total: {total})\n\n"
        "Poll kahan bhejna hai?",
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=keyboard,
    )
    return ANNOUNCEMENT_SELECT_GROUPS


# ══════════════════════════════════════════════════════════════
#   GROUP AUTO-REGISTER
# ══════════════════════════════════════════════════════════════

async def group_msg_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat = update.effective_chat
    user = update.effective_user
    if chat and chat.type in ["group", "supergroup"]:
        if user and is_admin(user.id):
            db.register_group(user.id, chat.id, chat.title or "Group")


async def bot_added_to_group(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat = update.effective_chat
    if not update.message or not update.message.new_chat_members:
        return
    for member in update.message.new_chat_members:
        if member.id == context.bot.id:
            added_by = update.message.from_user
            if added_by and is_admin(added_by.id):
                db.register_group(added_by.id, chat.id, chat.title or "Group")
                try:
                    await context.bot.send_message(
                        chat_id=chat.id,
                        text=(
                            f"✅ *Bot active hai!*\n\n"
                            f"*{chat.title}* register ho gaya.\n"
                            f"Ab is group mein announcements aa sakti hain."
                        ),
                        parse_mode=ParseMode.MARKDOWN,
                    )
                except Exception:
                    pass


# ══════════════════════════════════════════════════════════════
#   MAIN
# ══════════════════════════════════════════════════════════════

def main():
    app = Application.builder().token(BOT_TOKEN).build()

    conv = ConversationHandler(
        entry_points=[CommandHandler("start", start)],
        states={
            MAIN_MENU: [
                CallbackQueryHandler(menu_callback),
            ],
            ANNOUNCEMENT_TEXT: [
                CallbackQueryHandler(announcement_type, pattern="^ann_"),
                CallbackQueryHandler(menu_callback, pattern="^back_main$"),
                MessageHandler(filters.TEXT & ~filters.COMMAND, receive_text),
            ],
            WAIT_IMAGE: [
                MessageHandler(filters.PHOTO, receive_image),
                CallbackQueryHandler(menu_callback, pattern="^back_main$"),
            ],
            ANNOUNCEMENT_BUTTONS: [
                CallbackQueryHandler(add_button_prompt, pattern="^add_button$"),
                CallbackQueryHandler(goto_groups, pattern="^goto_groups$"),
                CallbackQueryHandler(skip_caption, pattern="^skip_caption$"),
                CallbackQueryHandler(menu_callback, pattern="^back_main$"),
            ],
            ADD_BUTTON_TEXT: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, receive_button),
                CallbackQueryHandler(goto_groups, pattern="^goto_groups$"),
                CallbackQueryHandler(add_button_prompt, pattern="^add_button$"),
            ],
            ANNOUNCEMENT_SELECT_GROUPS: [
                CallbackQueryHandler(group_select_callback,
                    pattern="^(toggle_|select_all|page_|confirm_groups|back_groups)"),
                CallbackQueryHandler(menu_callback, pattern="^back_main$"),
            ],
            VOTE_QUESTION: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, receive_vote_question),
                CallbackQueryHandler(menu_callback, pattern="^back_main$"),
            ],
            VOTE_OPTIONS: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, receive_vote_option),
                CallbackQueryHandler(vote_done, pattern="^vote_done$"),
                CallbackQueryHandler(menu_callback, pattern="^back_main$"),
            ],
            CONFIRM_SEND: [
                CallbackQueryHandler(confirm_callback),
                CallbackQueryHandler(menu_callback, pattern="^back_main$"),
            ],
        },
        fallbacks=[
            CommandHandler("start", start),
            CallbackQueryHandler(menu_callback, pattern="^back_main$"),
        ],
        per_user=True,
        per_chat=True,
    )

    app.add_handler(conv)
    app.add_handler(MessageHandler(
        filters.ChatType.GROUPS & ~filters.COMMAND, group_msg_handler
    ))
    app.add_handler(MessageHandler(
        filters.StatusUpdate.NEW_CHAT_MEMBERS, bot_added_to_group
    ))

    logger.info("✅ Bot started! Token active.")
    app.run_polling(drop_pending_updates=True)


if __name__ == "__main__":
    main()
