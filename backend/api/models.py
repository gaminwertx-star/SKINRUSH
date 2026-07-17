"""Data models for SKINRUSH.

Cases and their contents mirror the real cs-shot.pro catalog: every case holds
its own real skins with the source's real drop chance (%) and price. This is
what decides whether a player ends up + or - , so it is stored verbatim.
"""
from django.contrib.auth.models import User
from django.db import models
from django.utils.text import slugify

STARTING_BALANCE = 1500  # coins granted to a newly registered player

# Coin price. Quoted as a pack rather than a per-coin rate so the number the
# players are told ("22 000 so'm = 25 000 coin") is the number in the code.
TOPUP_PACK_SUM = 22_000     # so'm
TOPUP_PACK_COINS = 25_000   # coins that buys
TOPUP_MIN_SUM = 5_000       # smallest top-up we take


def coins_for_sum(amount_sum, bonus_percent=0):
    """Coins a player gets for `amount_sum` so'm, including any promo bonus."""
    base = amount_sum * TOPUP_PACK_COINS / TOPUP_PACK_SUM
    return int(round(base * (100 + bonus_percent) / 100))


class Case(models.Model):
    """A case in the catalog (real cs-shot.pro lineup)."""

    ext_id = models.CharField(max_length=64, blank=True, db_index=True)
    name = models.CharField(max_length=120, unique=True)
    slug = models.SlugField(max_length=140, unique=True, blank=True)
    price = models.PositiveBigIntegerField(help_text="Price in virtual coins/credits")
    image = models.CharField(max_length=400, help_text="Crate image URL")
    openings = models.PositiveBigIntegerField(default=0, help_text="Times opened on source")
    is_new = models.BooleanField(default=False)
    xp = models.IntegerField(default=0)
    sort_order = models.IntegerField(default=0, db_index=True)
    opens = models.PositiveBigIntegerField(default=0, help_text="Local opens")

    class Meta:
        ordering = ["sort_order", "price", "name"]

    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = slugify(self.name)
        super().save(*args, **kwargs)

    def __str__(self):
        return self.name


class CaseItem(models.Model):
    """A single real skin inside a case, with its real drop chance and price."""

    case = models.ForeignKey(Case, on_delete=models.CASCADE, related_name="items")
    name = models.CharField(max_length=180, db_index=True)   # base name, no wear
    weapon = models.CharField(max_length=100, blank=True)
    finish = models.CharField(max_length=140, blank=True)
    wear = models.CharField(max_length=40, blank=True)
    chance = models.FloatField(help_text="Drop chance in percent")
    price = models.PositiveBigIntegerField(help_text="Value in virtual coins")
    rarity = models.CharField(max_length=40, blank=True)
    color = models.CharField(max_length=9, blank=True)
    image = models.CharField(max_length=400)                 # steam image hash
    order = models.IntegerField(default=0)

    class Meta:
        ordering = ["order"]
        indexes = [models.Index(fields=["price"])]

    def __str__(self):
        return f"{self.name} ({self.wear}) — {self.chance}%"


class Drop(models.Model):
    """A record of a skin won from a case — powers the TOP DROPS feed."""

    case = models.ForeignKey(Case, on_delete=models.CASCADE, related_name="drops")
    item = models.ForeignKey(CaseItem, on_delete=models.CASCADE, related_name="drops")
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.item.name} ({self.case.name})"


class Player(models.Model):
    """A registered player (via Telegram). Holds the balance and profile shown
    in the admin panel."""

    # Optional link to a Django auth user (used to log the player into a session).
    user = models.OneToOneField(
        User, on_delete=models.CASCADE, related_name="player", null=True, blank=True
    )
    telegram_id = models.BigIntegerField(unique=True, null=True, blank=True, db_index=True)
    username = models.CharField(max_length=64, blank=True)     # Telegram @username / login name
    first_name = models.CharField(max_length=120, blank=True)
    photo_url = models.URLField(max_length=500, blank=True)
    # SKINRUSH account (email/username/phone + password login). Phone is unique
    # so it can be used to log in; null lets Telegram-only players omit it.
    phone = models.CharField(max_length=32, blank=True, null=True, unique=True, db_index=True)
    # Steam trade URL. Asked once on the first withdraw and reused after that;
    # the player can change it from the withdraw page.
    trade_url = models.URLField(max_length=300, blank=True)

    balance = models.BigIntegerField(default=STARTING_BALANCE)  # current coins
    coins_purchased = models.BigIntegerField(default=0)         # total coins ever bought
    total_won = models.BigIntegerField(default=0)              # total coins won (sold skins)
    streak = models.IntegerField(default=0)                    # consecutive daily-claim days
    invited_count = models.IntegerField(default=0)             # referred friends
    daily_day = models.IntegerField(default=0)                 # position in the 14-day cycle
    daily_claimed_date = models.DateField(null=True, blank=True)  # last daily claim
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)  # registered at
    last_seen = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]

    @property
    def display_name(self):
        return self.first_name or self.username or f"tg{self.telegram_id}"

    def __str__(self):
        return self.display_name


class OpenRecord(models.Model):
    """One skin a player has owned — the inventory and its whole history.

    Despite the name it covers every way a skin arrives (see `source`), not just
    case openings. Skin/case details are stored as a snapshot so the history
    survives a catalog re-seed (which recreates Case/CaseItem rows).
    """

    # How the skin arrived. Blank on rows written before this field existed —
    # their real source is unknowable, so they render as "—" rather than a guess.
    SRC_CASE, SRC_BATTLE, SRC_CONTRACT, SRC_UPGRADE, SRC_SHOP = (
        "case", "battle", "contract", "upgrade", "shop")
    SOURCES = [
        (SRC_CASE, "Keys"), (SRC_BATTLE, "Jang"), (SRC_CONTRACT, "Kontrakt"),
        (SRC_UPGRADE, "Yangilash"), (SRC_SHOP, "Do'kon"),
    ]
    # How the skin left, when `sold` is True. `sold` alone only says the skin is
    # gone; this says whether it was sold for coins, burned in an upgrade or a
    # contract, or really withdrawn to Steam — which is what the inventory tabs
    # and the "Holati" row need to tell apart. Blank while still owned.
    DISP_SOLD, DISP_UPGRADED, DISP_CONTRACT, DISP_WITHDRAWN = (
        "sold", "upgraded", "contract", "withdrawn")
    DISPOSITIONS = [
        (DISP_SOLD, "Sotilgan"), (DISP_UPGRADED, "Yangilashga ketgan"),
        (DISP_CONTRACT, "Kontraktga ketgan"), (DISP_WITHDRAWN, "Chiqarilgan"),
    ]

    player = models.ForeignKey(Player, on_delete=models.CASCADE, related_name="opens")
    case = models.ForeignKey(Case, on_delete=models.SET_NULL, null=True, blank=True)
    case_name = models.CharField(max_length=120)
    skin_name = models.CharField(max_length=180)
    skin_image = models.CharField(max_length=400, blank=True)
    skin_price = models.BigIntegerField(default=0)
    rarity = models.CharField(max_length=40, blank=True)
    color = models.CharField(max_length=9, blank=True)
    wear = models.CharField(max_length=40, blank=True)
    # Real Steam Market value. No price source feeds this yet, so it stays null
    # and the UI shows "—"; never derive it from skin_price, the two are not
    # proportional.
    steam_price_usd = models.DecimalField(max_digits=10, decimal_places=2,
                                          null=True, blank=True)
    source = models.CharField(max_length=16, choices=SOURCES, blank=True,
                              db_index=True)
    # Consumed: sold for coins, fed into an upgrade/contract, or withdrawn to
    # Steam. Anything with sold=True has left the inventory for good; `disposition`
    # says which of those happened.
    sold = models.BooleanField(default=False)
    disposition = models.CharField(max_length=16, choices=DISPOSITIONS, blank=True)
    # Held by an open WithdrawRequest — still the player's, but on its way to
    # Steam, so it must not be sellable/upgradable/contractable meanwhile.
    # Cleared again if the request is rejected.
    is_locked = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.skin_name} <- {self.case_name}"


class Battle(models.Model):
    """A real multiplayer case battle lobby.

    The creator opens a lobby with N seats and a list of cases (rounds), paying
    the entry cost for seat 0. Other real players join open seats (no bots), each
    paying the same entry cost. When every seat is filled the battle is resolved:
    every player opens the same rounds, and the player with the highest total drop
    value wins ALL the dropped skins (they land in the winner's inventory).
    """

    player = models.ForeignKey(Player, on_delete=models.CASCADE, null=True, blank=True,
                               related_name="battles")          # creator (seat 0)
    session_key = models.CharField(max_length=60, blank=True, db_index=True)
    n_players = models.IntegerField(default=2)
    case_ids = models.JSONField(default=list)          # ordered rounds (repeats allowed)
    total_cost = models.BigIntegerField(default=0)     # entry cost per player
    # waiting (lobby open) | completed (resolved) | cancelled (refunded)
    status = models.CharField(max_length=16, default="waiting")
    seats = models.JSONField(default=list)             # [{seat, player_id, name, photo, streak}]
    winner_index = models.IntegerField(null=True, blank=True)
    pot = models.BigIntegerField(default=0)            # total value of all dropped skins
    paid = models.BooleanField(default=False)          # prize already credited to winner?
    data = models.JSONField(default=dict)              # {cases, results:[{seat,player,drops,total}]}
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"Battle #{self.pk} ({self.n_players}p, {self.total_cost})"


class WithdrawRequest(models.Model):
    """A request to move a won skin out to the player's real Steam inventory.

    Nothing here is automated: an admin reads the request in the panel, sends the
    trade offer by hand in Steam, and walks the row along
    ``pending -> approved -> sent -> completed`` (or ``rejected``). Every step
    notifies the player over the Telegram bot.

    The skin itself is `record`; while the request is open the record is locked
    so it cannot also be sold, upgraded or burned in a contract. A rejection
    unlocks it, a completion marks it sold (it now lives in real Steam).
    """

    PENDING, APPROVED, SENT, COMPLETED, REJECTED = (
        "pending", "approved", "sent", "completed", "rejected")
    STATUSES = [
        (PENDING, "Kutilmoqda"), (APPROVED, "Tasdiqlandi"), (SENT, "Yuborildi"),
        (COMPLETED, "Yakunlandi"), (REJECTED, "Rad etildi"),
    ]
    # A player may hold only one request in these states at a time.
    OPEN_STATUSES = (PENDING, APPROVED, SENT)

    player = models.ForeignKey(Player, on_delete=models.CASCADE,
                               related_name="withdraws")
    record = models.ForeignKey(OpenRecord, on_delete=models.CASCADE,
                               related_name="withdraws")
    # Snapshots, kept for the log the same way OpenRecord snapshots its skin:
    # they must stay readable even if the catalog or the player's URL changes.
    case_name = models.CharField(max_length=120, blank=True)
    trade_url = models.URLField(max_length=300)
    status = models.CharField(max_length=16, default=PENDING, choices=STATUSES,
                              db_index=True)
    reject_reason = models.CharField(max_length=300, blank=True)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    updated_at = models.DateTimeField(auto_now=True)   # bumped on every status move

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.record.skin_name} -> {self.player} ({self.status})"


class PaymentAdmin(models.Model):
    """A person who takes real money and tops players up by hand.

    Payments are settled off-platform: the player transfers so'm to this
    admin's own card and sends a receipt over the bot. Nothing here touches a
    payment provider — the site only introduces the two of them and records the
    outcome.
    """

    tg_chat_id = models.BigIntegerField(unique=True, db_index=True)
    name = models.CharField(max_length=120)
    card_number = models.CharField(max_length=32)
    card_holder = models.CharField(max_length=120)
    is_active = models.BooleanField(default=True, db_index=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["name"]

    def __str__(self):
        return self.name or f"admin {self.tg_chat_id}"


class PromoCode(models.Model):
    """A top-up bonus code. The admin picks both the code and the percentage —
    nothing here is hard-coded to a particular code or a particular bonus."""

    code = models.CharField(max_length=32, unique=True, db_index=True)  # stored upper-case
    bonus_percent = models.IntegerField(default=0)
    is_active = models.BooleanField(default=True)
    uses = models.IntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def save(self, *args, **kwargs):
        self.code = (self.code or "").strip().upper()
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.code} (+{self.bonus_percent}%)"


class TopUpRequest(models.Model):
    """A player asking to buy coins, and the conversation that settles it.

    `waiting`  — filed, the chosen admin has been pinged but has not opened it
    `connected`— admin took it; the two are relaying messages through the bot
    `paid`     — admin credited the coins
    `closed`   — admin hung up (or it was abandoned) without payment
    """

    WAITING, CONNECTED, PAID, CLOSED = "waiting", "connected", "paid", "closed"
    STATUSES = [
        (WAITING, "Kutilmoqda"), (CONNECTED, "Aloqada"),
        (PAID, "To'landi"), (CLOSED, "Yopilgan"),
    ]
    # While a request is in one of these the player has a live conversation, so
    # they cannot open a second one.
    OPEN_STATUSES = (WAITING, CONNECTED)

    player = models.ForeignKey(Player, on_delete=models.CASCADE, related_name="topups")
    admin = models.ForeignKey(PaymentAdmin, on_delete=models.SET_NULL, null=True,
                              blank=True, related_name="topups")
    amount_sum = models.BigIntegerField()          # so'm the player typed
    coins = models.BigIntegerField()               # coins promised, bonus included
    promo = models.ForeignKey(PromoCode, on_delete=models.SET_NULL, null=True,
                              blank=True, related_name="topups")
    bonus_percent = models.IntegerField(default=0)  # snapshot: promos can change
    status = models.CharField(max_length=16, default=WAITING, choices=STATUSES,
                              db_index=True)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.player} · {self.amount_sum} so'm ({self.status})"


class CoinPurchase(models.Model):
    """A coin top-up / purchase by a player."""

    player = models.ForeignKey(Player, on_delete=models.CASCADE, related_name="purchases")
    amount = models.BigIntegerField()
    note = models.CharField(max_length=120, blank=True)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"+{self.amount} ({self.player})"
