"""Owner-scoped pagination shared by public lists."""
import discord


class Pagination(discord.ui.View):
    def __init__(self, records, owner_id, title, render, per_page=5):
        super().__init__(timeout=180)
        self.records = list(records)
        self.owner_id = owner_id
        self.title = title
        self.render = render
        self.per_page = per_page
        self.page = 0
        self.message = None
        self.update_buttons()

    async def interaction_check(self, interaction):
        if interaction.user.id != self.owner_id:
            await interaction.response.send_message("ページ送りは表示した本人のみ操作できます。", ephemeral=True)
            return False
        return True

    def update_buttons(self):
        self.previous.disabled = self.page == 0
        self.next.disabled = (self.page + 1) * self.per_page >= len(self.records)

    def embed(self):
        embed = discord.Embed(title=self.title, color=discord.Color.blue())
        start = self.page * self.per_page
        for record in self.records[start:start + self.per_page]:
            name, value = self.render(record)
            embed.add_field(name=name[:256], value=value[:1024] or "—", inline=False)
        pages = max(1, (len(self.records) + self.per_page - 1) // self.per_page)
        embed.set_footer(text=f"{self.page + 1}/{pages} ページ · 全{len(self.records)}件")
        return embed

    async def on_timeout(self):
        for button in self.children:
            button.disabled = True
        if self.message:
            try:
                await self.message.edit(view=self)
            except discord.HTTPException:
                pass

    async def on_error(self, interaction, error, item):
        from command_errors import send_error
        await send_error(interaction, error)

    @discord.ui.button(label="◀ 前へ", style=discord.ButtonStyle.primary)
    async def previous(self, interaction, button):
        self.page = max(0, self.page - 1)
        self.update_buttons()
        await interaction.response.edit_message(embed=self.embed(), view=self)

    @discord.ui.button(label="次へ ▶", style=discord.ButtonStyle.primary)
    async def next(self, interaction, button):
        self.page = min((len(self.records) - 1) // self.per_page, self.page + 1)
        self.update_buttons()
        await interaction.response.edit_message(embed=self.embed(), view=self)
