# macosvm

**Crie e gerencie VMs macOS no Linux, com a GPU virtual do reims-vgpu.**

`macosvm` é um gerenciador de máquinas virtuais macOS para Linux. Ele não
implementa a emulação: ele dirige o [reims-vgpu](https://github.com/steelbrain/reims-vgpu)
e o [reims-util](https://github.com/steelbrain/reims-util), que já fazem a
GPU virtual, a imagem do OpenCore e os instaladores do macOS.

O que ele acrescenta é a parte que ninguém tinha feito de forma aberta: um
diagnóstico do computador, a preparação do ambiente, a importação de discos
que já têm macOS, backup em um arquivo só, rede com ponte, início automático
com a sessão e um menu de terminal.

---

## Por que este projeto existe

O ecossistema de VMs macOS no Linux tem duas metades, e só uma delas é
aberta:

| Peça | O que faz | Licença |
| --- | --- | --- |
| [reims-vgpu](https://github.com/steelbrain/reims-vgpu) | A GPU virtual (Metal no macOS, Vulkan no Linux), o QEMU que a usa e o `reims-ctl` | GPL-2.0-or-later OU LGPL-3.0-or-later |
| [reims-util](https://github.com/steelbrain/reims-util) | A imagem do OpenCore com a identidade do Mac, o OVMF e os instaladores do macOS | GPL-2.0-or-later OU LGPL-3.0-or-later |
| **Gerenciadores** | Criar, listar, iniciar, manter, diagnosticar | geralmente fechados e pagos |

O trabalho difícil — a paravirtualização gráfica, a identidade do Mac, os
instaladores verificados contra os chunklists da Apple — já está aberto e
bem feito. O que costuma ficar fechado é a cola em volta: o `setup`, o
`doctor`, o menu, o backup, a ponte de rede.

Este projeto é essa cola, aberta. Sem assinatura, sem `.deb` fechado, sem
canal no Discord.

### O que este projeto **não** é

- **Não é um fork do OSX-REIMS, do UTM, do OSX-KVM ou do PROXMOX.** Nada
  aqui vem do código de nenhum deles.
- **Não usa código proprietário.** Foi escrito a partir da documentação
  pública do reims-vgpu e do reims-util, e do comportamento observável
  desses programas. Nenhum binário fechado foi decompilado, inspecionado ou
  enviado a uma ferramenta de IA. A licença do OSX-REIMS proíbe tudo isso —
  e, mesmo permitindo, não seria o caminho direito: o upstream aberto já
  entrega tudo o que é preciso.
- **Não distribui macOS.** O macOS é baixado da Apple, pelo computador do
  usuário, e verificado contra a assinatura da Apple.

---

## Requisitos

- Linux x86_64, com KVM (`/dev/kvm`) e virtualização habilitada no BIOS.
- Uma GPU com Vulkan 1.2 ou mais, e o driver correspondente instalado.
- Rust 1.98.1 ou mais novo (para compilar o reims-vgpu).
- O `reims-vgpu` compilado e o `reims-util` instalado.

`macosvm doctor` confere tudo isso e diz o que falta.

## Instalação

```bash
git clone https://github.com/seu-usuario/macos-vm-manager
cd macos-vm-manager
pip install --user .          # ou: pipx install .
```

Depois, prepare o computador:

```bash
macosvm setup
```

O `setup` instala os pacotes de compilação da sua distribuição, ajusta o
kernel (`vm.max_map_count`), põe o seu usuário no grupo certo, compila o
reims-vgpu e instala o reims-util. Ele é idempotente: rodar de novo pula o
que já está pronto. Com `--dry-run`, ele diz o que faria e não toca em nada.

## Uso

```bash
macosvm                        # o menu
macosvm list                   # as VMs
macosvm create mac             # uma VM nova, com macOS da Apple
macosvm start mac              # liga
macosvm stop mac               # desliga
macosvm import outra --disk ~/macos.qcow2   # adota um disco já instalado
macosvm backup mac             # salva a VM em um arquivo só
macosvm restore mac-20260101-120000.tar.gz
macosvm doctor                 # o que está faltando
macosvm network on             # ponte: a VM ganha um endereço próprio
macosvm autostart on mac       # a VM abre com a sessão
```

Cada VM guarda as próprias configurações (memória, processadores, tela, GPU,
som, rede) e vale a partir da próxima inicialização.

### O menu

```
macosvm
```

O menu faz as mesmas coisas que os comandos, e cada ação do menu também
existe como comando, para quem prefere o terminal ou quer automatizar.

---

## O que está implementado

| Comando | O que faz |
| --- | --- |
| `setup` | Preparar o computador: pacotes, kernel, grupos, reims-vgpu, reims-util |
| `doctor` | Conferir o computador, sem mudar nada. `--json` para um programa |
| `list` | As VMs e o estado de cada uma. `--json` |
| `create` | Uma VM nova, com instalador da Apple ou um de sua escolha |
| `import` | Adotar um disco QCOW2 que já tem macOS, com identidade nova |
| `start` `stop` `reset` `poweroff` `term` | O ciclo de vida da VM |
| `show` `set` | As configurações da VM |
| `backup` `restore` | A VM inteira em um arquivo `.tar.gz`, e de volta |
| `network` | A ponte, e pôr uma VM nela |
| `autostart` | Um serviço de usuário do systemd, que liga a VM com a sessão |
| `logs` | Onde estão os logs de cada VM |
| `tui` | O menu |

## O que ainda não está

- A imagem do OpenCore é a do `reims-util`, com a identidade que ele gera.
  Não há ainda uma EFI com mais ajustes (SSDTs, kexts extras) escolhida por
  perfil de hardware.
- A ponte de rede move o endereço do computador para a ponte e põe a porta
  física sob ela. Não há a opção de escolher a rede por VM com mais de uma
  ponte.
- Não há interface gráfica; só o terminal.
- Sem testes de integração: os testes cobrem a lógica, não uma VM de verdade.

---

## Notas legais

- **A licença do macOS permite o uso do macOS somente em hardware Apple.**
  Rodar macOS em uma VM sobre PC é uso em hardware que não é Apple, e é
 illegal sob os termos da Apple. Isto é o mesmo que qualquer projeto de
  hackintosh ou de VMs macOS que exista. Use para estudo e experimento, e
  compre um Mac se precisar do macOS no dia a dia.
- **A Apple não está associada a este projeto.** macOS e Apple são marcas da
  Apple Inc. O reims-vgpu e o macosvm são projetos independentes, sem
  patrocínio nem aprovação da Apple.
- **`macosvm` é MIT.** Ele chama o `reims-ctl` e o `reims-util` como
  programas separados; as licenças deles (GPL-2.0-or-later OU
  LGPL-3.0-or-later) valem para eles e para os arquivos que eles
  distribuem.

## Contribuindo

Este projeto é novo e pequeno. As coisas que mais ajudam:

1. **Um relato de bug** com a saída de `macosvm doctor` e o trecho do log
   que importa. Nenhum dado de identidade das VMs: o `doctor` não os tem.
   O modelo está em [.github/ISSUE_TEMPLATE](.github/ISSUE_TEMPLATE/bug-report.yml).
2. **Uma correção** — abra um PR, rode os testes antes:
   ```bash
   python -m unittest discover -s tests -v
   ruff check . && ruff format --check .
   ```
3. **Uma EFI melhor.** A parte mais frágil hoje é o OpenCore: um perfil de
   hardware, com os ajustes que ele precisa, seria uma contribuição grande.

As convenções do projeto estão em [CLAUDE.md](CLAUDE.md).

## Licença

MIT — veja [LICENSE](LICENSE). O que este projeto usa, de quem é e sob que
licença está em [NOTICE.md](NOTICE.md).

O `macosvm` é MIT porque ele **chama** o `reims-ctl` e o `reims-util` como
programas separados, sem embutir nem modificar o código deles. Se um dia ele
passar a fazer isso, a licença muda para uma compatível com a deles — e a
decisão se toma antes de escrever o código.

