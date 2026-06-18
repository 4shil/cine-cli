<a name="readme-top"></a>

[![Stargazers][stars-shield]][stars-url]
[![Pypi Version][pypi-shield]][pypi-url]
[![Pypi Downloads][pypi-dl-shield]][pypi-stats-url]
[![Python Versions][python-shield]][pypi-url]
[![Issues][issues-shield]][issues-url]
[![MIT License][license-shield]][license-url]



  <sub>Watch everything from your terminal.</sub>
  <br>
  <br>
  <a href="https://github.com/cine-cli/cine-cli/issues">Report Bug</a>
  ·
  <a href="https://github.com/cine-cli/cine-cli/issues">Request Feature</a>

  <br>
  <br>
 
</div>
<br>

> [!Warning]
> ## cine-cli is in an unmaintained state!
> This project has been in an unmaintained state for a long while now. I made an announcement on the discord regarding the future of cine-cli a few months ago, now it's time to quote it here on the readme:
> 
> ... I don't think I'll be maintaining the cine-cli project anymore (including handling issues) going forward, as I'm extremely occupied with life and other work and projects that are more important to me.
> Mov-cli was actually never really my project, its founder is [Poseidon444](https://github.com/Poseidon444). The project was later taken by [Ananas](https://github.com/ananasmoe), then I came in far later into the project.
> 
> Anyways, we all began contributing less and less to the project as we used it less and less eventually resulting in the development halting and some leaving the project. Now it's just me and the initial founder of the project left 
> and I really do not have much spare time anymore, and to be completely honest, I also don't have much personal reason to resume with the development of the project **in the current way it is**.
> 
> I do have work in progress plans for a potential reboot of cine-cli but that is at the bottom of my priority list and I'll need a team to maintain many parts of it as I want maintenance to be low. As I cannot promise this, it's better to say I will be stepping away from the project than promise a sequel. This doesn't mean the tool will spontaneously combust. Some plugins should still continue to work.
> 
> For now, Goodbye! 👋
> 
> *~* [*Goldy*](https://github.com/THEGOLDENPRO)

> [!Warning]
> ~~You may have noticed, development slowing down and halting for a long while.
> This is because I and the other contributors sadly no longer have the time to take this project to the next level (v4.5).~~
>
> ~~This isn't the end, v4.4 may still continue to receive bug fixes here and there, but v4.4 is currently on
> [feature freeze](https://en.wikipedia.org/wiki/Freeze_(software_engineering)), so new features will only be added once [v4.5 development](https://github.com/cine-cli/cine-cli/issues/352) begins again.
> [v4.5](https://github.com/cine-cli/cine-cli/tree/v4.5) is a rewrite.~~
>
> ~~We are hoping we have the time and motivation to return one day, hopefully with more contributors to help this time.~~

> [!Note]
> v4 is constantly changing so be sure to **keep the tool and your plugins up to date**. Also, I would advise not using it as a library yet as the API still has many breaking changes.

## What is cine-cli? 💫

<div align="center">

  <img width="800px" src="https://github.com/cine-cli/cine-cli/assets/66202304/fa78b38c-0df0-464a-a78e-cb8a04cdc885">

</div>

**cine-cli** is a command line tool with plugin support that streamlines the process of streaming media from the comfort of your terminal; ~~*so you can show off to your friends the superiority of the command line.*~~ 💪 The tool is sort of a framework that handles metadata, configuration and scraping of the media to be streamed in your media player of choice.

**cine-cli** [is **not** a piracy tool](./disclaimer.md); in fact, we encourage the opposite through the existence of our plugins [cine-cli-files](https://github.com/cine-cli/cine-cli-files) and [cine-cli-jellyplex](https://github.com/cine-cli/cine-cli-jellyplex). 🫵 You obtain the media. You pick the plugins.

## Installation 🛠️

> [!TIP]
> For in-depth installation instructions hit the [wiki](https://github.com/cine-cli/cine-cli/wiki/Installation).

### Prerequisites
- **A supported platform:**
  - Linux
  - Windows
  - FreeBSD (https://github.com/cine-cli/cine-cli/issues/359)
  - Android (via [Termux](https://termux.dev/en/))
  - iOS (via [iSH Shell](https://ish.app/))
  - MacOS
- **[python](https://www.python.org/downloads/)** (**required**, with pip)
- **[lxml](https://pypi.org/project/lxml/)** (optional, ⚡ faster scraping)
- **[fzf](https://github.com/junegunn/fzf?tab=readme-ov-file#installation)** (optional but **highly recommended**)
- **[mpv](https://mpv.io/installation/)** (recommended & default media player)

To get running these are all the prerequisites you'll need.

With the prerequisites installed, cine-cli can be installed via the pip command on all platforms with Python version 3.10 or above.

```sh
pip install cine-cli -U
```
> Check out the [wiki on installation](https://github.com/cine-cli/cine-cli/wiki/Installation) for more in-depth guidance on installing cine-cli.

## Usage 🖱️
[!showcase video](https://github.com/cine-cli/cine-cli/assets/132799819/d924c3f5-775c-46a3-97f5-ff27433b69dd)

cine-cli comes packaged with a CLI interface via the `cine-cli` command you can use in your respective terminal. 

> [!NOTE]
> You may notice cine-cli doesn't ship with any scrapers (or previously known as providers) by default, this is because v4 is plugin-based and scrapers are now part of plugins that must be chosen to be installed.
> Find out how to do so at the [wiki](https://github.com/cine-cli/cine-cli/wiki#plugins).

1. Install the plugin of your choice. Visit this [wiki page](https://github.com/cine-cli/cine-cli/wiki/Plugins) on how to do so and the [cine-cli-plugin](https://github.com/topics/cine-cli-plugin) topic for a list of **third-party** cine-cli plugins.
```sh
pip install cine-cli-youtube
```
> This is just an example.
> If you are struggling, visit that [wiki page](https://github.com/cine-cli/cine-cli/wiki/Plugins).

2. Add the plugin to your config.
```sh
cine-cli -e
```
Alternatively, you may also edit by manually opening the config file. See this [Wiki page](https://github.com/cine-cli/cine-cli/wiki/Configuration#introduction) on that.  
```toml
[cine-cli.plugins]
youtube = "cine-cli-youtube"
```
> Check out the [wiki](https://github.com/cine-cli/cine-cli/wiki/Plugins) for more in-depth explanation.

3. Scrape away!
```sh
cine-cli -s youtube blender studio
```
<img src="https://github.com/cine-cli/cine-cli/assets/132799819/f7a75a14-105b-4afa-9075-bb2d937baa25">

> The command above searches for `blender studio` with our [youtube](https://github.com/cine-cli/cine-cli-youtube) plugin, **however once again cine-cli is plugin based and there are many of them [in the wild](https://github.com/topics/cine-cli-plugin). 😉**

## Star Graph ⭐
[![Star Graph Chart](https://api.star-history.com/svg?repos=cine-cli/cine-cli&type=Date)](https://star-history.com/#cine-cli/cine-cli&Date)

## Contributing ✨
Pull requests are welcome and *appreciated*. For major changes, please open an issue first to discuss what you would like to change.

<a href = "https://github.com/cine-cli/cine-cli/graphs/contributors">
  <img src = "https://contrib.rocks/image?repo=cine-cli/cine-cli"/>
</a>

## Inspiration 🌟
Inspired by [ani-cli](https://github.com/pystardust/ani-cli), [lobster](https://github.com/justchokingaround/lobster) and [animdl](https://github.com/justfoolingaround/animdl)

<!-- MARKDOWN LINKS & IMAGES -->
<!-- https://www.markdownguide.org/basic-syntax/#reference-style-links -->
[contributors-shield]: https://img.shields.io/github/contributors/cine-cli/cine-cli.svg?style=for-the-badge
[contributors-url]: https://github.com/cine-cli/cine-cli/graphs/contributors
[forks-shield]: https://img.shields.io/github/forks/cine-cli/cine-cli.svg?style=for-the-badge
[forks-url]: https://github.com/cine-cli/cine-cli/network/members
[stars-shield]: https://img.shields.io/github/stars/cine-cli/cine-cli?style=flat
[stars-url]: https://github.com/cine-cli/cine-cli/stargazers
[pypi-shield]: https://img.shields.io/pypi/v/cine-cli?style=flat
[pypi-url]: https://pypi.org/project/cine-cli/
[pypi-stats-url]: https://pypistats.org/packages/cine-cli
[python-shield]: https://img.shields.io/pypi/pyversions/cine-cli?style=flat
[issues-shield]: https://img.shields.io/github/issues/cine-cli/cine-cli?style=flat
[issues-url]: https://github.com/cine-cli/cine-cli/issues
[license-shield]: https://img.shields.io/github/license/cine-cli/cine-cli?style=flat
[license-url]: ./LICENSE
[pypi-dl-shield]: https://img.shields.io/pypi/dm/cine-cli?color=informational&label=pypi%20downloads
