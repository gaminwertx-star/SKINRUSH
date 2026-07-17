"""Data models for SKINRUSH.

Cases and their contents mirror the real cs-shot.pro catalog: every case holds
its own real skins with the source's real drop chance (%) and price. This is
what decides whether a player ends up + or - , so it is stored verbatim.
"""
from django.contrib.auth.models import User
from django.db import models
from django.utils.text import slugify

STARTING_BALANCE = 1500  # coins granted to a newly registered player


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
    """One case-opening by a player — 'which case gave what' history.

    Skin/case details are stored as a snapshot so the history survives a catalog
    re-seed (which recreates Case/CaseItem rows)."""

    player = models.ForeignKey(Player, on_delete=models.CASCADE, related_name="opens")
    case = models.ForeignKey(Case, on_delete=models.SET_NULL, null=True, blank=True)
    case_name = models.CharField(max_length=120)
    skin_name = models.CharField(max_length=180)
    skin_image = models.CharField(max_length=400, blank=True)
    skin_price = models.BigIntegerField(default=0)
    rarity = models.CharField(max_length=40, blank=True)
    color = models.CharField(max_length=9, blank=True)
    wear = models.CharField(max_length=40, blank=True)
    # Consumed: sold for coins, fed into an upgrade/contract, or withdrawn to
    # Steam. Anything with sold=True has left the inventory for good.
    sold = models.BooleanField(default=False)
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
