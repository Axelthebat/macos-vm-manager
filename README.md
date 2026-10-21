# macosvm

Gerenciador de VMs macOS para Linux, construído sobre o
[reims-vgpu](https://github.com/steelbrain/reims-vgpu).

O `macosvm` não emula nada. Ele dirige o `reims-ctl` e o `reims-util`, dois
programas livres que já fazem a parte difícil: a GPU virtual, a imagem do
OpenCore e os instaladores do macOS. O que falta no ecossistema é a gerência
dessas VMs em um computador de mesa, e é o que este projeto entrega.

## O que já é livre

| Projeto | Função | Licença |
| --- | --- | --- |
| [reims-vgpu](https://github.com/steelbrain/reims-vgpu) | GPU virtual (Metal no macOS, Vulkan no Linux), o QEMU que a usa e o `reims-ctl` | GPL-2.0-or-later OU LGPL-3.0-or-later |
| [reims-util](https://github.com/steelbrain/reims-util) | Imagem do OpenCore com a identidade do Mac, OVMF e os instaladores do macOS | GPL-2.0-or-later OU LGPL-3.0-or-later |

A paravirtualização gráfica, a identidade do Mac por VM e os instaladores
verificados contra a assinatura da Apple já são software livre. O que costuma
vir fechado é a gerência: preparação do ambiente, diagnóstico, importação de
discos, backup, rede, início automático.

## O que este projeto acrescenta

- `setup`: prepara o computador, do zero, em passos que podem ser repetidos.
- `doctor`: aponta o que falta e como corrigir, sem mudar nada.
- `import`: adota um disco QCOW2 que já tem macOS, com identidade nova.
- `backup` e `restore`: a VM inteira em um arquivo `.tar.gz`.
- `network`: uma ponte de rede, para a VM receber um endereço próprio.
- `autostart`: um serviço do systemd que liga a VM com a sessão.
- `tui`: um menu de terminal, em que toda ação também existe como comando.

## O que este projeto não faz

- Não é um fork do OSX-REIMS, do UTM, do OSX-KVM ou do PROXMOX, e não usa
  código de nenhum deles.
- Não usa código proprietário. Foi escrito a partir da documentação pública
  do reims-vgpu e do reims-util e do comportamento observável desses
  programas. Nenhum binário fechado foi decompilado, inspecionado ou enviado
  a uma ferramenta de IA.
- Não distribui macOS. O instalador vem da Apple, pelo computador do usuário,
  e o reims-util confere a assinatura da Apple antes de usá-lo.

## Requisitos

- Linux x86_64, com KVM (`/dev/kvm`) e virtualização habilitada no firmware.
- GPU com Vulkan 1.2 ou superior e o driver correspondente no sistema. A GPU
  não precisa de suporte nativo do macOS: é a GPU virtual que o macOS vê.
- rustup, com Rust 1.98.1 ou mais novo. O reims-vgpu fixa a versão do Rust
  no `rust-toolchain.toml`, e só o rustup lê essa fixação.
- O reims-vgpu compilado e o reims-util instalado.

`macosvm doctor` confere cada item e diz o que fazer quando falta algo.

## Instalação

```bash
git clone https://github.com/Axelthebat/macos-vm-manager
cd macos-vm-manager
./install.sh --system-deps
```

O script instala o `macosvm` em um ambiente próprio
(`~/.local/share/macosvm/venv`) e cria o comando em `~/.local/bin/macosvm`.
A flag `--system-deps` instala os pacotes de compilação da distribuição, e é
a única etapa que pede sudo. Sem ela, o script instala só o gerenciador.

Depois, prepare o computador:

```bash
macosvm setup
```

O `setup` executa seis passos: instala os pacotes que faltam, instala o
rustup, ajusta `vm.max_map_count`, põe o usuário no grupo do `/dev/kvm` e do
`/dev/udmabuf`, compila o reims-vgpu e instala o reims-util. Passos já
concluídos são pulados, e `--dry-run` imprime o plano sem executar nada.

Quem prefere instalar o gerenciador por conta própria:

```bash
pipx install .                # ou: pip install --user .
```

## Uso

```bash
macosvm                        # o menu
macosvm list                   # as VMs e o estado de cada uma
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

Cada VM guarda as próprias configurações (processadores, memória, tela, GPU,
som, rede) e vale a partir da próxima inicialização.

O menu se desenha na tela e navega com as setas. Sem um terminal em que
desenhar, ele pergunta por número.

## Comandos

| Comando | O que faz |
| --- | --- |
| `setup` | Prepara o computador: pacotes, rustup, kernel, grupos, reims-vgpu, reims-util |
| `doctor` | Confere o computador sem mudar nada. `--json` para um programa |
| `list` | As VMs e o estado de cada uma. `--json` |
| `create` | Uma VM nova, com instalador da Apple ou um de sua escolha |
| `import` | Adota um disco QCOW2 que já tem macOS, com identidade nova |
| `start` `stop` `reset` `poweroff` `term` | Ciclo de vida da VM |
| `show` `set` | As configurações da VM |
| `backup` `restore` | A VM inteira em um arquivo `.tar.gz`, e de volta |
| `network` | A ponte, e pôr uma VM nela |
| `autostart` | Um serviço de usuário do systemd, que liga a VM com a sessão |
| `logs` | Onde estão os logs de cada VM |
| `tui` | O menu |

## Desempenho

O macOS instalado numa VM sobre PC não é rápido como um Mac, e a instalação
é a parte mais lenta de todas. Três motivos, e o que fazer com cada um:

**O instalador roda com renderização por software.** A vGPU só tem driver
dentro do macOS instalado. O instalador e o Recovery não têm esse driver, e
o upstream compensa expondo o framebuffer de firmware no dispositivo, que o
macOS desenha na CPU do host. A tela do instalador fica pesada, e o trabalho
de verdade (copiar os arquivos, rodar os scripts do instalador) vai a bem.

A补救 que ajuda é baixar a resolução durante a instalação, porque cada
pixel desenhado por software custa:

```bash
macosvm set mac --resolution 1280x800
```

Vale a pena para VMs novas:

```bash
macosvm create mac --macos tahoe
macosvm set mac --resolution 1280x800
```

**A memória do host é o recurso raro.** O reims-ctl dá à VM metade da
memória do computador, entre 4 e 16 GB. Com 16 GB no host, sobram 8 GB para
tudo o mais, e o cache de página do Linux fica pequeno, o que atrapalha a
escrita de dezenas de gigabytes da instalação. Feche o que estiver pesado
enquanto instala.

**O disco é NVMe, mas o guest enxerga um IDE que finge ser rotacional.** O
QEMU que o upstream compila anexa o disco como `ide-hd` com
`rotation_rate=1`. Não há como mudar isso pela linha de comando sem mexer no
QEMU: o `reims-ctl` monta o `-drive` do disco, e um segundo `-drive` com o
mesmo identificador faz o QEMU recusar subir.

Depois que a instalação acaba, a vGPU entra em ação e o desktop usa a
aceleração de verdade. A diferença é grande.

## Limites conhecidos

- A imagem do OpenCore é a do reims-util, com a identidade que ele gera. Não
  há uma EFI com ajustes por perfil de hardware.
- A ponte move o endereço do computador para ela e põe a porta física sob
  ela. Só existe uma ponte, e ela serve a todas as VMs que estão nela.
- Só o terminal. Não há interface gráfica.
- Os testes cobrem a lógica, não uma VM em funcionamento. Não há teste de
  integração.
- O caminho de hóspede x86_64 é o que o reims-vgpu valida no Linux. O
  reims-util baixa instaladores do macOS 10.13 ao 26.

## Questões legais

A licença do macOS permite o seu uso somente em hardware Apple. Rodar macOS
em uma VM sobre PC é uso em hardware que não é Apple, e é ilegal sob os
termos da Apple. O destino deste projeto é estudo, experimento e teste em
ambiente descartável. Quem precisa do macOS para trabalhar deve comprar um
Mac.

macOS e Apple são marcas da Apple Inc. Este projeto não é afiliado,
patrocinado nem aprovado pela Apple Inc. O mesmo vale para o reims-vgpu e
para o reims-util, que são projetos independentes.

O `macosvm` é MIT porque chama o `reims-ctl` e o `reims-util` como programas
separados, sem embutir nem modificar o código deles. As licenças de cada
dependência estão em [NOTICE.md](NOTICE.md). Se o projeto passar a modificar
esse código, a licença do macosvm passa a ter que ser compatível com a
deles, e a decisão se toma antes de escrever o código.

## Contribuindo

1. **Relato de bug.** Inclua a saída do `macosvm doctor` e o trecho do log
   que importa. O `doctor` não tem número de série nem outro dado de
   identidade das VMs, então pode ser colado inteiro. O modelo está em
   [.github/ISSUE_TEMPLATE](.github/ISSUE_TEMPLATE/bug-report.yml).
2. **Correção.** Abra um PR e rode os testes antes:
   ```bash
   python -m unittest discover -s tests -v
   ruff check . && ruff format --check .
   ```
3. **Uma EFI melhor.** A parte mais frágil hoje é o OpenCore. Um perfil de
   hardware, com os ajustes que ele precisa, resolveria a maior limitação do
   projeto.

As convenções de código estão em [CLAUDE.md](CLAUDE.md).

## Licença

MIT. O texto está em [LICENSE](LICENSE).
