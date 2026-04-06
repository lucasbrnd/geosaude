# <p align="center">

# &#x20; <img src="data/logo\_geosaude.png" alt="GeoSaúde" width="400"/>

# </p>

# 

# <p align="center">

# &#x20; Ferramenta de apoio à decisão para escolha do local de maior viabilidade 

# &#x20; para implantação de uma nova unidade de saúde no espaço urbano.

# </p>

# Desenvolvida no âmbito de uma tese de doutorado do **Programa de Engenharia de Transportes** da **Escola de Engenharia de São Carlos (EESC) — Universidade de São Paulo (USP)**.

\---

## Autoria

**Lucas Brandão Monteiro de Assis**
Departamento de Engenharia de Transporte — EESC/USP

**Orientadores**

* Prof. Dr. Paulo Cesar Lima Segantine — EESC/USP
* Prof. Dr. Miguel José das Neves Pires Amado — Instituto Superior Técnico / ULisboa

\---

## Descrição

O GeoSaúde é uma ferramenta computacional que combina dados geoespaciais, socioeconômicos e de acessibilidade para identificar locais prioritários para a implantação de novas unidades de saúde em áreas urbanas. A análise é baseada em nove critérios ponderados que avaliam diferentes dimensões do território municipal.

\---

## Critérios de Análise

|Critério|Descrição|Fonte|
|-|-|-|
|C1|Vulnerabilidade Social|IVS (IPEA) / IPVS (SEADE)|
|C2|Distribuição Demográfica|Censo 2022 (IBGE)|
|C3|Distribuição de Renda|Censo 2022 (IBGE)|
|C4|Tempo mínimo de deslocamento|OSM + r5py|
|C5|Nível de acesso (FCA)|OSM + r5py|
|C6|Cobertura das unidades existentes|OSM + r5py|
|C7|Risco de Eventos Naturais|SGB|
|C8|Proximidade a Equipamentos Indesejáveis|OpenStreetMap|
|C9|Proximidade a Equipamentos Desejáveis|CNES + Mapa Social|

\---

## Requisitos

* Python 3.10+
* Anaconda ou Miniconda (recomendado)
* Java 11+ (necessário para o r5py)
* Chave de API HERE Geocoding
* Chave de API OpenTopography

\---

## Instalação

### 1\. Clonar o repositório

```bash
git clone https://github.com/lucasbrnd/geosaude.git
cd geosaude
```

### 2\. Criar o ambiente conda

```bash
conda create -n GeoSaude python=3.10
conda activate GeoSaude
```

### 3\. Instalar as dependências

```bash
pip install -r requirements.txt
```

### 4\. Configurar as chaves de API

Crie um arquivo `.env` na raiz do projeto baseado no `.env.example`:

```bash
cp .env.example .env
```

Edite o `.env` com suas chaves:

```
HERE\_API\_KEY=sua\_chave\_aqui
OPENTOPO\_API\_KEY=sua\_chave\_aqui
```

As chaves podem ser obtidas em:

* **HERE:** https://developer.here.com
* **OpenTopography:** https://opentopography.org

\---

## Estrutura do Projeto

```
geosaude/
├── main.py                  # Script de execução principal
├── geosaude.py              # Módulo com os critérios C1–C9
├── geocnes.py               # Módulo de coleta e geocodificação do CNES
├── utils.py                 # Funções utilitárias
├── report.py                # Geração do relatório PDF
├── dashboard.py             # Geração do dashboard
├── example.ipynb            # Notebook de exemplo de uso
├── requirements.txt         # Dependências do projeto
├── .env.example             # Modelo de configuração das APIs
└── data/
    ├── ivs.gpkg             # Atlas de Vulnerabilidade Social (IPEA)
    ├── ivs\_mun.csv          # Tabela de municípios IVS
    ├── ipvs.gpkg            # Índice Paulista de Vulnerabilidade Social (SEADE)
    ├── ipvs\_mun.csv         # Tabela de municípios IPVS
    ├── sgb\_mun1.csv         # Links de dados SGB por município
    └── logo\_geosaude.png    # Logotipo do GeoSaúde
```

Os dados do Censo 2022 (IBGE) e da rede OSM são baixados automaticamente durante a execução.

\---

## Uso

### Via Jupyter Notebook

Abra o `example.ipynb` e execute a célula de configuração:

```python
import os
from dotenv import load\_dotenv
load\_dotenv()

from main import main

main(
    mun                   = "Nome do Município",
    uf                    = "UF",
    here\_api              = os.getenv("HERE\_API\_KEY"),
    opentopo\_api          = os.getenv("OPENTOPO\_API\_KEY"),
    forcar\_reprocessamento = False   # True para reprocessar tudo
)
```

### Via linha de comando

```bash
python main.py
```

\---

## Saídas

Para cada município processado, o GeoSaúde gera os seguintes arquivos em `./data/resultados/{município}/`:

```
resultados/
└── {município}/
    ├── raster/              # Rasters individuais de cada critério (.tif)
    ├── cnes\_{mun}\_{uf}\_02.gpkg   # Unidades de APS geocodificadas
    ├── cnes\_{mun}\_{uf}\_05.gpkg   # Hospitais geocodificados
    ├── cnes\_{mun}\_{uf}\_73.gpkg   # UPAs geocodificadas
    ├── geosaude\_{mun}.gpkg       # Resultado final vetorial
    ├── relatorio\_{mun}.pdf       # Relatório de análise
    ├── dashboard\_{mun}.html      # Dashboard interativo
    └── geosaude\_{mun}\_{uf}.log   # Log de execução
```

\---

## Dependências de Dados Externos

|Dado|Fonte|Acesso|
|-|-|-|
|Censo 2022 — Setores Censitários|IBGE|Automático|
|Censo 2022 — CNEFE|IBGE|Automático|
|Censo 2022 — Renda|IBGE|Automático|
|Rede viária OSM|BBBike Extract|Automático|
|Modelo de elevação|OpenTopography|API key|
|Estabelecimentos CNES|DATASUS|Automático|
|Equipamentos sociais|Mapa Social (MDS)|Automático|
|Equipamentos OSM|OpenStreetMap|Automático|
|IVS|IPEA|Incluído no repositório|
|IPVS|SEADE|Incluído no repositório|
|Suscetibilidade natural|SGB|Automático|

\---

## Licença

Este projeto está licenciado sob a **Creative Commons Attribution 4.0 International (CC BY 4.0)**.

Você pode copiar, distribuir e adaptar o material para qualquer finalidade, inclusive comercial, desde que atribua os devidos créditos ao autor original.

[!\[CC BY 4.0](https://licensebuttons.net/l/by/4.0/88x31.png)](https://creativecommons.org/licenses/by/4.0/)

\---

## Citação

Se utilizar o GeoSaúde em sua pesquisa, cite como:

```
ASSIS, Lucas Brandão Monteiro de. GeoSaúde: ferramenta de apoio à decisão 
para implantação de unidades de saúde no espaço urbano. 
Tese (Doutorado em Engenharia de Transportes) — Escola de Engenharia de 
São Carlos, Universidade de São Paulo, São Carlos, 2026.
```

\---

## Contato

Lucas Brandão Monteiro de Assis
Departamento de Engenharia de Transporte — EESC/USP
GitHub: [@lucasbrnd](https://github.com/lucasbrnd)

