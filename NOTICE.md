# NOTICE

`macosvm` é software livre sob a licença MIT (veja [LICENSE](LICENSE)).

Este arquivo diz o que `macosvm` usa, de quem é, e sob que licença. Ele não
anexa nenhum código de terceiros: o `macosvm` **chama** programas de terceiros
como processos separados, e não os redistribute.

## Dependências de execução

| Componente | O que é | Licença | Onde fica |
| --- | --- | --- | --- |
| [reims-vgpu](https://github.com/steelbrain/reims-vgpu) | A GPU virtual, o QEMU que a usa e o `reims-ctl` | GPL-2.0-or-later OU LGPL-3.0-or-later | Compilado em `~/.local/share/reims-ctl/qemu`, instalado pelo `macosvm setup` |
| [reims-util](https://github.com/steelbrain/reims-util) | A imagem do OpenCore, o OVMF e os instaladores do macOS | GPL-2.0-or-later OU LGPL-3.0-or-later | `cargo install --locked --git https://github.com/steelbrain/reims-util` |
| [QEMU](https://www.qemu.org) | O emulador, na árvore do reims-vgpu | GPL-2.0-or-later | Dentro da árvore do reims-vgpu |
| [OpenCore](https://github.com/acidanthera/OpenCorePkg) | O firmware de boot | BSD-3-Clause | Baixado pelo reims-util |
| [Lilu](https://github.com/acidanthera/Lilu) | O kext que o plugin `ReimsVgpu.kext` usa | BSD-3-Clause | Baixado pelo reims-util |
| [OcBinaryData](https://github.com/acidanthera/OcBinaryData) | Os ícones e o som de boot do OpenCore | BSD-3-Clause | Baixado pelo reims-util |
| [OVMF](https://github.com/tianocore/edk2) | O firmware UEFI | BSD-2-Clause | Baixado pelo reims-util |
| [macrecovery](https://github.com/acidanthera/OpenCorePkg) / `macserial` | As ferramentas de recuperação e de identidade | BSD-3-Clause | Dentro do reims-util |
| [metal2vulkan](https://github.com/steelbrain/metal2vulkan) | A camada que leva Metal para Vulkan | A licença dos autores (veja o repositório) | Compilado com o reims-vgpu |
| [SDL3](https://github.com/libsdl-org/SDL) | A janela da VM no Linux | zlib | Compilado com o reims-vgpu |
| Python 3.11+ | O interpretador do `macosvm` | PSF-2.0 | Do sistema |

## Por que MIT

O `macosvm` não contém, não modifica e não redistribui nenhum arquivo dos
programas acima. Ele os executa como processos separados, com a interface de
linha de comando que eles publicam — como um script de shell que chama o
`gcc`. Isso não faz do `macosvm` uma obra derivada dos programas GPL: as
licenças deles valem para eles, para os arquivos que eles distribuem e para as
modificações que alguém fizer neles.

Se um dia o `macosvm` passar a embutir ou a modificar código do reims-vgpu ou
do reims-util, a licença do `macosvm` tem que mudar para uma compatível
(GPL-2.0-or-later ou LGPL-3.0-or-later, à escolha de quem recebe). Isso é
uma decisão a tomar antes, não depois.

## macOS

O `macosvm` **não contém nem distribui macOS**. O macOS é baixado pelo
computador do usuário, direto dos servidores da Apple, e verificado contra a
assinatura da Apple pelo reims-util. A licença do macOS vale para o macOS, e
permite o seu uso somente em hardware Apple.

macOS e Apple são marcas da Apple Inc. Este projeto não é afiliado,
patrocinado nem aprovado pela Apple Inc.
