from asyncio import Lock, sleep
from io import BytesIO
from os import remove
from subprocess import call

from aiohttp import ClientSession
from discord import (
    Client,
    Embed,
    File,
    Intents,
    Interaction,
    InteractionResponded,
    User,
    app_commands,
)
from numpy import array, copy
from PIL import Image


class DumpyClient(Client):
    def __init__(self):
        super().__init__(intents=Intents.all())
        self.tree = app_commands.CommandTree(self)
        self.tree.on_error = self.interaction_error
        self.lock = Lock()

    async def interaction_error(
        self, interaction: Interaction, error: app_commands.AppCommandError
    ) -> None:
        embed = Embed(color=0xE74C3C, description="❌ " + str(error))

        try:
            await interaction.response.send_message(embed=embed)  # noqa
        except InteractionResponded:
            await interaction.followup.send(embed=embed)

    async def setup_hook(self) -> None:
        await self.tree.sync()


client = DumpyClient()


@client.tree.command(description="Convert a user's profile picture into crewmates.")
async def dump(inter: Interaction, user: User | None = None, size: int = 15) -> None:
    await inter.response.defer()  # noqa

    user = user or inter.user
    avatar = user.avatar or user.default_avatar

    async with client.lock:

        async with ClientSession() as session:
            response = await session.get(avatar.url)
            content = await response.read()

        image = Image.open(BytesIO(content))
        image.save("input.png", "png")

        frames = []
        frames_data = []

        for i in range(6):
            frame = Image.open(f"frames/{i}.png").convert("RGBA")
            frames.append(frame)
            frames_data.append(array(frame))

        frame_width, frame_height = frames[0].size

        input_ = Image.open("input.png").convert("RGB")
        input_width, input_height = input_.size

        output_height = int(
            size * (input_height / input_width) * (frame_width / frame_height)
        )
        output_px = int(size * frame_width), int(size * frame_height)

        input_scaled = input_.resize((size, output_height), Image.NEAREST)  # noqa

        for i in range(6):
            await sleep(0)

            bg = Image.new(mode="RGBA", size=output_px)

            for j in range(output_height):
                for k in range(size):

                    r, g, b = input_scaled.getpixel((k, j))

                    data = copy(frames_data[(i + k - j) % len(frames)])
                    red, green, blue, alpha = data.T

                    c1 = (red == 214) & (green == 224) & (blue == 240)
                    data[..., :-1][c1.T] = r, g, b

                    c2 = (red == 131) & (green == 148) & (blue == 191)
                    data[..., :-1][c2.T] = (
                        int(r * 2 / 3),
                        int(g * 2 / 3),
                        int(b * 2 / 3),
                    )

                    new_frame = Image.fromarray(data)

                    bg.paste(new_frame, (k * frame_width, j * frame_height))

            bg.save(f"output_{i}.png")

            # it is assumed that ffmpeg.exe is in the current working directory
            call(
                'ffmpeg -f image2 -i output_%d.png -filter_complex "[0:v] '
                "scale=sws_dither=none:,split [a][b];[a] palettegen=max_colors=255:stats_mode=single "
                '[p];[b][p] paletteuse=dither=none" -r 20 -y -hide_banner -loglevel error output.gif',
                shell=True,
            )

        for i in range(6):
            remove(f"output_{i}.png")

        f = File("output.gif", filename="output.gif")

        embed = Embed(color=0x5865F2)
        embed.set_image(url="attachment://output.gif")
        embed.set_author(name=user, icon_url=avatar.url)

        await inter.followup.send(embed=embed, file=f)  # noqa


if __name__ == "__main__":

    with open("token.txt") as file:
        token = file.read()

    client.run(token)
