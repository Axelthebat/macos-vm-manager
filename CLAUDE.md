# CLAUDE.md

Convenções do `macosvm`. Vale para quem escreve código aqui, e para os
agentes que revisam.

## O que o projeto é

Um gerenciador de VMs macOS para Linux. Ele **não** implementa emulação: ele
dirige o `reims-ctl` e o `reims-util`, que são software livre e fazem o
trabalho pesado (a GPU virtual, a imagem do OpenCore, os instaladores).

Regra que decorre disso: **nada de código do OSX-REIMS, do UTM, do OSX-KVM ou
do PROXMOX**. Nada decompilado, nada copiado. A referência é a documentação
pública do reims-vgpu e do reims-util, e o comportamento observável desses
programas.

## Estilo

- Python 3.11+, só a biblioteca padrão. Sem dependências de runtime.
- `ruff check` e `ruff format` passam. A linha tem no máximo 110 colunas.
- Cada arquivo começa com `# SPDX-License-Identifier: MIT`.
- Docstrings no estilo do que já está no projeto: uma linha que diz o que a
  coisa é, e o porquê quando não for óbvio. Comentários explicam *por que*,
  nunca *o que*.
- Nomes explícitos. `vms.py` tem `list_vms`, `find_vm`, `resolve_vm` — não
  `get`, `fetch` ou `run`.

## Estrutura

| Arquivo | Responsabilidade |
| --- | --- |
| `macosvm/cli.py` | A linha de comando: argumentos e saída |
| `macosvm/config.py` | Os caminhos (XDG) e as settings |
| `macosvm/reims.py` | Achar e rodar o `reims-ctl` e o `reims-util` |
| `macosvm/vms.py` | As VMs: registro, listar, criar, importar, backup |
| `macosvm/doctor.py` | As verificações do computador |
| `macosvm/setup.py` | Preparar o computador |
| `macosvm/net.py` | A ponte de rede |
| `macosvm/autostart.py` | O serviço do systemd |
| `macosvm/ui.py` | Cor, prompt, tabela |
| `macosvm/tui.py` | O menu |

A regra que corta quase todo o debate: **os comandos falam com o `reims-ctl`
pelos argumentos dele, e nunca editam os arquivos do reims-ctl por baixo dos
panos.** A única exceção é o registro de VMs (`vms.toml`), porque o
`reims-ctl` não tem comando para registrar uma VM que o `macosvm` mesmo
colocou no lugar — e isso está comentado no código, em `vms.write_registry`.

## Erros

- Uma falha vira `RuntimeError` com uma mensagem que diz o que fazer, não
  só o que deu errado. O usuário lê isso.
- `ui.err` escreve em stderr; `ui.ok`/`ui.info`, em stdout. `doctor` sai com
  1 quando há alguma falha, 0 quando não há (avisos não falham).
- `argparse` cuida da validação dos argumentos. Não reescreva isso à mão.

## Testes

`python -m unittest discover -s tests`. Sem dependências, sem rede.

- Toda função pura tem teste: o registro, as settings, os backups, o
  diagnóstico, o parser.
- Um teste que depende do computador (KVM, Vulkan) é raro e explica por quê
  ele não pode correr em todo lugar.
- Ao mexer em `vms.py`, mexa em `tests/test_vms.py`. O mesmo vale para os
  outros.

## Licença

MIT. Todo arquivo novo traz o cabeçalho SPDX. `NOTICE.md` lista as
dependências e as licenças delas. Se um dia o `macosvm` passar a embutir
código do reims-vgpu ou do reims-util, a licença muda para GPL-2.0-or-later
ou LGPL-3.0-or-later — e isso se decide antes de escrever o código, não
depois.
