# ======================================================
# BOM DIA ABENÇOADO PARA O PADRINHO
# ======================================================
#
# O que faz (todos os dias às 06:00, via Agendador de Tarefas do Windows):
#   1. Abre (ou reaproveita) o Chrome com o WhatsApp Web já logado.
#   2. Pesquisa "bom dia abençoado" no Google Imagens.
#   3. Escolhe uma imagem que ainda NÃO foi enviada (guarda histórico).
#   4. Baixa a imagem e converte para JPG.
#   5. Abre a conversa do padrinho e envia a imagem com uma legenda.
#
# Se o Google falhar (mudou a página, sem internet...), usa uma imagem da
# pasta "imagens_reserva" (opcional), para o padrinho não ficar sem o bom dia.
#
# Como rodar manualmente:
#   py bom_dia_padrinho.py              -> envia de verdade
#   py bom_dia_padrinho.py --teste      -> só baixa a imagem, NÃO envia
#
# Primeira vez:
#   - Defina o número do contato (uma vez só, no Prompt de Comando):
#         setx PADRINHO_TELEFONE "55XXXXXXXXXXX"
#   - Rode "py bom_dia_padrinho.py --teste". O Chrome vai abrir com um perfil
#     próprio (pasta PERFIL_CHROME). Abra web.whatsapp.com nele e escaneie
#     o QR Code. O login fica salvo nesse perfil.
#   - Deixe esse Chrome aberto (ou não: o script abre sozinho se precisar).
# ======================================================

import argparse
import base64
import hashlib
import json
import logging
import os
import random
import socket
import subprocess
import sys
import time
from datetime import datetime
from io import BytesIO
from pathlib import Path
from urllib.parse import quote

import requests
from PIL import Image
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait
from selenium.common.exceptions import (
    TimeoutException, WebDriverException, StaleElementReferenceException
)
from selenium.webdriver.common.action_chains import ActionChains
import win32clipboard   # pywin32: copiar a imagem para a área de transferência

# ======================================================
# CONFIGURAÇÕES — ajuste aqui
# ======================================================

# Número do contato no formato internacional: 55 + DDD + número, só dígitos.
# Lido da variável de ambiente PADRINHO_TELEFONE, para o número real ficar
# só no seu computador (e não no GitHub). Para definir, uma vez só:
#     setx PADRINHO_TELEFONE "55XXXXXXXXXXX"
# Celulares no Brasil têm 9 dígitos (9 na frente); se a conversa não abrir,
# tente o número sem o 9.
PADRINHO_TELEFONE = os.getenv("PADRINHO_TELEFONE", "55XXXXXXXXXXX")

# Legenda enviada junto com a imagem (pode usar emoji).
LEGENDA = "Bom dia, padrinho! Que Deus abençoe o seu dia 🙏"

# Termos de pesquisa: um é sorteado a cada dia, para variar as imagens.
TERMOS_PESQUISA = [
    "bom dia abençoado",
    "bom dia abençoado mensagem",
    "bom dia com Deus",
    "bom dia abençoado lindo",
]

# Pasta do projeto (onde este arquivo está).
PASTA_BASE = Path(__file__).resolve().parent

# Perfil EXCLUSIVO do Chrome para a automação (o login do WhatsApp fica aqui).
# Não pode ser o perfil padrão do seu Chrome: desde a versão 136 o Chrome
# bloqueia automação no perfil padrão, por segurança.
PERFIL_CHROME = PASTA_BASE / "perfil_chrome_whatsapp"

# Caminho do Chrome no Windows (ajuste se o seu estiver em outro lugar).
CHROME_EXE = r"C:\Program Files\Google\Chrome\Application\chrome.exe"

# Porta usada para o Selenium "conversar" com o Chrome já aberto.
PORTA_DEBUG = 9222

PASTA_IMAGENS = PASTA_BASE / "imagens_enviadas"   # imagens baixadas
PASTA_RESERVA = PASTA_BASE / "imagens_reserva"    # opcional: imagens de backup
ARQUIVO_HISTORICO = PASTA_BASE / "historico.json" # evita repetir imagem
ARQUIVO_LOG = PASTA_BASE / "bom_dia.log"

# Tempos máximos de espera (segundos)
TIMEOUT_WHATSAPP = 90   # WhatsApp Web pode demorar para sincronizar
TIMEOUT_GOOGLE = 20

# ======================================================
# LOG (arquivo + console)
# ======================================================

logging.basicConfig(
    level=logging.INFO,
    format="[%(asctime)s] [%(levelname)s] %(message)s",
    handlers=[
        logging.FileHandler(ARQUIVO_LOG, encoding="utf-8"),
        logging.StreamHandler(sys.stdout),
    ],
)
log = logging.getLogger("bom_dia")


# ======================================================
# 1. CHROME — conectar no que está aberto (ou abrir)
# ======================================================

def porta_aberta(porta):
    """Verifica se já existe um Chrome escutando na porta de debug."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.settimeout(1)
        return s.connect_ex(("127.0.0.1", porta)) == 0


def abrir_chrome_se_preciso():
    """
    Se o Chrome da automação não estiver aberto, abre com:
      --remote-debugging-port -> permite o Selenium se conectar
      --user-data-dir         -> perfil próprio, onde o WhatsApp fica logado
    """
    if porta_aberta(PORTA_DEBUG):
        log.info("Chrome da automação já está aberto — reaproveitando")
        return

    log.info("Abrindo o Chrome da automação...")
    PERFIL_CHROME.mkdir(parents=True, exist_ok=True)
    subprocess.Popen([
        CHROME_EXE,
        f"--remote-debugging-port={PORTA_DEBUG}",
        f"--user-data-dir={PERFIL_CHROME}",
        "--start-maximized",
        "https://web.whatsapp.com",
    ])

    # Aguarda o Chrome subir
    for _ in range(30):
        if porta_aberta(PORTA_DEBUG):
            time.sleep(2)
            return
        time.sleep(1)
    raise RuntimeError("Chrome não abriu a porta de debug a tempo")


def conectar_chrome():
    """Conecta o Selenium ao Chrome já aberto (não abre um Chrome novo)."""
    abrir_chrome_se_preciso()
    opcoes = Options()
    opcoes.add_experimental_option("debuggerAddress", f"127.0.0.1:{PORTA_DEBUG}")
    # O Selenium 4 baixa o chromedriver compatível sozinho (Selenium Manager)
    return webdriver.Chrome(options=opcoes)


# ======================================================
# 2. HISTÓRICO — para não repetir imagem
# ======================================================

def carregar_historico():
    try:
        return json.loads(ARQUIVO_HISTORICO.read_text(encoding="utf-8"))
    except Exception:
        return {"urls": [], "hashes": []}


def salvar_historico(historico):
    # Mantém só os últimos 365 registros
    historico["urls"] = historico["urls"][-365:]
    historico["hashes"] = historico["hashes"][-365:]
    ARQUIVO_HISTORICO.write_text(
        json.dumps(historico, indent=2, ensure_ascii=False), encoding="utf-8"
    )


def hash_imagem(conteudo):
    return hashlib.sha256(conteudo).hexdigest()


# ======================================================
# 3. GOOGLE IMAGENS — pesquisar e baixar uma imagem
# ======================================================

# JavaScript executado na página do Google: lista as imagens visíveis
# com tamanho razoável (ignora ícones e logos pequenos).
JS_LISTAR_IMAGENS = """
return [...document.images]
  .filter(i => i.naturalWidth >= 150 && i.naturalHeight >= 150)
  .filter(i => i.src && (i.src.startsWith('http') || i.src.startsWith('data:image')))
  .map(i => ({src: i.src, w: i.naturalWidth, h: i.naturalHeight}));
"""


# Clica na imagem cujo src é igual ao informado (retorna false se não achar).
JS_CLICAR_POR_SRC = """
const img = [...document.images].find(i => i.src === arguments[0]);
if (!img) return false;
img.scrollIntoView({block: 'center'});
img.click();
return true;
"""


def baixar_conteudo(src):
    """Baixa a imagem (URL http) ou decodifica (data:image;base64)."""
    if src.startswith("data:image"):
        return base64.b64decode(src.split(",", 1)[1])

    resp = requests.get(
        src,
        timeout=20,
        headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"},
    )
    resp.raise_for_status()
    if not resp.headers.get("Content-Type", "").startswith("image"):
        raise ValueError("URL não retornou uma imagem")
    return resp.content


def converter_para_jpg(conteudo, destino):
    """
    Converte para JPG. Importante: imagens .webp enviadas pelo WhatsApp
    podem virar FIGURINHA. Em JPG, sempre chegam como foto.
    """
    img = Image.open(BytesIO(conteudo))
    if img.width < 250 or img.height < 250:
        raise ValueError(f"Imagem muito pequena ({img.width}x{img.height})")
    img.convert("RGB").save(destino, "JPEG", quality=92)
    return destino


def buscar_imagem_google(driver, historico):
    """
    Pesquisa no Google Imagens e devolve o caminho de um JPG baixado.

    Estratégia:
      a) Clica numa miniatura sorteada -> o Google abre o painel lateral
         com a imagem em alta resolução (URL do site original).
      b) Se não conseguir a alta resolução, usa a própria miniatura.
    O seletor das miniaturas muda com frequência no Google, por isso
    usamos JavaScript genérico (todas as <img> grandes), não classes CSS.
    """
    termo = random.choice(TERMOS_PESQUISA)
    log.info(f"Pesquisando no Google Imagens: '{termo}'")

    # Abre em uma ABA NOVA para não mexer na aba do WhatsApp
    driver.switch_to.new_window("tab")
    try:
        # udm=2 = aba "Imagens" do Google
        driver.get(f"https://www.google.com/search?q={quote(termo)}&udm=2&hl=pt-BR")
        WebDriverWait(driver, TIMEOUT_GOOGLE).until(
            lambda d: len(d.execute_script(JS_LISTAR_IMAGENS)) >= 5
        )

        # Guardamos só o "src" (texto) das miniaturas, e não o elemento:
        # o Google recria a página ao clicar, e elementos antigos dariam
        # erro de "stale element". Para clicar, localizamos de novo pelo src.
        vistas = []
        for i in driver.execute_script(JS_LISTAR_IMAGENS):
            if i["src"] not in vistas:
                vistas.append(i["src"])
        candidatas = vistas[:30]   # só as primeiras (mais relevantes)
        random.shuffle(candidatas)

        for src_mini in candidatas[:10]:
            if src_mini in historico["urls"]:
                continue

            # a) tenta a versão em alta: clica e procura imagem grande nova
            src_alta = None
            try:
                antes = {i["src"] for i in driver.execute_script(JS_LISTAR_IMAGENS)}
                clicou = driver.execute_script(JS_CLICAR_POR_SRC, src_mini)
                if not clicou:
                    raise WebDriverException("miniatura não está mais na página")
                time.sleep(2.5)
                depois = driver.execute_script(JS_LISTAR_IMAGENS)
                novas = [
                    i for i in depois
                    if i["src"] not in antes
                    and i["src"].startswith("http")
                    and "gstatic.com" not in i["src"]
                    and i["w"] >= 400
                ]
                if novas:
                    src_alta = max(novas, key=lambda i: i["w"] * i["h"])["src"]
            except WebDriverException:
                pass

            # b) baixa (alta resolução primeiro, miniatura como alternativa)
            for src in [s for s in (src_alta, src_mini) if s]:
                try:
                    conteudo = baixar_conteudo(src)
                    h = hash_imagem(conteudo)
                    if h in historico["hashes"]:
                        log.info("Imagem já enviada antes — tentando outra")
                        break

                    PASTA_IMAGENS.mkdir(exist_ok=True)
                    destino = PASTA_IMAGENS / f"{datetime.now():%Y-%m-%d}.jpg"
                    converter_para_jpg(conteudo, destino)

                    historico["urls"].append(src_mini)
                    historico["hashes"].append(h)
                    log.info(f"Imagem baixada ({'alta' if src == src_alta else 'miniatura'}): {destino.name}")
                    return destino
                except Exception as e:
                    log.info(f"Imagem descartada ({type(e).__name__}: {e})")

        raise RuntimeError("Nenhuma imagem válida encontrada no Google")

    finally:
        # Fecha a aba do Google (as outras abas continuam como estavam)
        driver.close()
        driver.switch_to.window(driver.window_handles[0])


def imagem_reserva():
    """Sorteia uma imagem da pasta imagens_reserva (plano B)."""
    if not PASTA_RESERVA.exists():
        return None
    arquivos = [
        p for p in PASTA_RESERVA.iterdir()
        if p.suffix.lower() in (".jpg", ".jpeg", ".png")
    ]
    return random.choice(arquivos) if arquivos else None


# ======================================================
# 4. WHATSAPP WEB — enviar a imagem
# ======================================================
# O WhatsApp muda o HTML com frequência. Por isso os elementos são buscados
# por listas de seletores alternativos ou por JavaScript com nomes parciais.

SELETORES_CAIXA_MENSAGEM = [
    "footer div[contenteditable='true']",
    "div[contenteditable='true'][data-tab='10']",
]

# O botão Enviar da pré-visualização muda de nome entre versões do WhatsApp
# (ex.: data-icon "send", "wds-ic-send-filled"...). Por isso a busca é por
# nome PARCIAL, feita em JavaScript:
#   - qualquer elemento com data-icon contendo "send", ou
#   - aria-label contendo "Enviar"/"Send"
# Só aceita elementos visíveis e NA FRENTE (nada cobrindo o centro), ignora
# a lista de conversas (lado esquerdo) e, se houver mais de um, escolhe o
# mais embaixo/à direita, que é onde fica o botão de envio.
JS_ACHAR_BOTAO_ENVIAR = """
const visivel = e => { const r = e.getBoundingClientRect();
  if (!r.width || !r.height || getComputedStyle(e).visibility === 'hidden') return false;
  const t = document.elementFromPoint(r.left + r.width / 2, r.top + r.height / 2);
  return t && (t === e || e.contains(t) || t.contains(e)); };
const lateral = document.querySelector('#pane-side');
const candidatos = [...document.querySelectorAll(
    "[data-icon*='send' i], [aria-label*='enviar' i], [aria-label*='send' i]")]
  .filter(e => visivel(e) && !(lateral && lateral.contains(e)));
if (!candidatos.length) return null;
candidatos.sort((a, b) => {
  const ra = a.getBoundingClientRect(), rb = b.getBoundingClientRect();
  return (rb.bottom + rb.right) - (ra.bottom + ra.right);
});
// devolve o elemento clicável (o botão que envolve o ícone)
return candidatos[0].closest("button, [role='button']") || candidatos[0];
"""

# Diagnóstico: lista ícones e rótulos visíveis no lado direito da tela.
# Vai para o log quando o botão não é encontrado, para facilitar o ajuste.
JS_DIAGNOSTICO_BOTOES = """
return [...document.querySelectorAll('[data-icon], [aria-label]')]
  .filter(e => { const r = e.getBoundingClientRect();
                 return r.width > 0 && r.left > window.innerWidth / 2; })
  .map(e => (e.getAttribute('data-icon') || '') + ' | ' + (e.getAttribute('aria-label') || ''))
  .slice(-40);
"""

# Campo de legenda da pré-visualização.
# A caixa de mensagem normal da conversa continua existindo POR BAIXO da
# pré-visualização. Para não pegar ela, só aceitamos campos que estejam
# realmente NA FRENTE: o elemento no centro do campo tem que ser o próprio
# campo (document.elementFromPoint). Também ignoramos o footer.
# Se houver mais de um, preferimos o que tem "legenda"/"caption" no rótulo.
JS_ACHAR_LEGENDA = """
const naFrente = e => { const r = e.getBoundingClientRect();
  if (!r.width || !r.height) return false;
  const t = document.elementFromPoint(r.left + r.width / 2, r.top + r.height / 2);
  return t && (t === e || e.contains(t)); };
const campos = [...document.querySelectorAll("div[contenteditable='true']")]
  .filter(e => naFrente(e) && !e.closest('footer'));
if (!campos.length) return null;
const rotulo = e => ((e.getAttribute('aria-label') || '') + ' ' +
                     (e.getAttribute('aria-placeholder') || '')).toLowerCase();
return campos.find(e => /legenda|caption/.test(rotulo(e))) || campos[campos.length - 1];
"""

# Descreve um elemento no log (ajuda a entender o que foi clicado)
JS_DESCREVER = """
const e = arguments[0];
return (e.tagName || '') + ' | data-icon=' + (e.getAttribute('data-icon') ||
  (e.querySelector('[data-icon]')?.getAttribute('data-icon') || '')) +
  ' | aria-label=' + (e.getAttribute('aria-label') || '');
"""


def esperar_qualquer(driver, seletores, timeout, clicavel=False):
    """Espera até QUALQUER um dos seletores aparecer. Retorna o elemento."""
    condicao = EC.element_to_be_clickable if clicavel else EC.presence_of_element_located
    fim = time.time() + timeout
    while time.time() < fim:
        for sel in seletores:
            try:
                return WebDriverWait(driver, 1).until(condicao((By.CSS_SELECTOR, sel)))
            except TimeoutException:
                continue
    raise TimeoutException(f"Nenhum seletor encontrado: {seletores}")


def focar(driver, elemento):
    """
    Coloca o cursor no elemento SEM clicar (via JavaScript).
    O .click() do Selenium dava ElementClickInterceptedException quando
    havia outra camada da tela por cima.
    """
    driver.execute_script("arguments[0].focus();", elemento)
    time.sleep(0.3)


def digitar_texto(driver, elemento, texto):
    """
    Digita texto com emoji. O send_keys do ChromeDriver não aceita emoji
    (caracteres fora do BMP), então usamos o insertText do navegador.
    """
    focar(driver, elemento)
    driver.execute_script("document.execCommand('insertText', false, arguments[0]);", texto)


def ir_para_aba_whatsapp(driver):
    """
    Muda para a aba do WhatsApp Web. Se você tiver outras abas abertas
    nesse Chrome, elas não são tocadas. Se não houver aba do WhatsApp,
    abre uma nova.
    """
    for aba in driver.window_handles:
        driver.switch_to.window(aba)
        if "web.whatsapp.com" in driver.current_url:
            return
    driver.switch_to.new_window("tab")


def copiar_imagem(caminho_imagem):
    """
    Copia a imagem para a área de transferência do Windows, como se você
    tivesse clicado com o botão direito > Copiar imagem.

    Colando (Ctrl+V) na conversa, o WhatsApp abre a pré-visualização como
    FOTO (com legenda). É mais estável que o menu Anexar, cujos campos de
    arquivo escondidos mudam entre versões (e um deles é de figurinha).

    O Windows guarda imagens no formato DIB = arquivo BMP sem os 14 bytes
    iniciais de cabeçalho; por isso o [14:].
    """
    img = Image.open(caminho_imagem).convert("RGB")
    buffer = BytesIO()
    img.save(buffer, "BMP")
    dados_dib = buffer.getvalue()[14:]

    win32clipboard.OpenClipboard()
    try:
        win32clipboard.EmptyClipboard()
        win32clipboard.SetClipboardData(win32clipboard.CF_DIB, dados_dib)
    finally:
        win32clipboard.CloseClipboard()


def previa_aberta(campo_legenda):
    """
    A pré-visualização está aberta enquanto o campo de legenda existir e
    estiver visível. Depois do envio, o WhatsApp remove esse campo da tela
    (o Selenium acusa 'stale'), e é assim que confirmamos o envio.
    """
    if campo_legenda is None:
        return False
    try:
        return campo_legenda.is_displayed()
    except StaleElementReferenceException:
        return False


def enviar_imagem_whatsapp(driver, caminho_imagem, legenda):
    log.info("Abrindo a conversa no WhatsApp Web...")
    ir_para_aba_whatsapp(driver)

    # Link direto da conversa (funciona mesmo se o contato não estiver salvo)
    driver.get(f"https://web.whatsapp.com/send?phone={PADRINHO_TELEFONE}")

    # Espera a caixa de mensagem: indica que a conversa abriu
    try:
        caixa = esperar_qualquer(driver, SELETORES_CAIXA_MENSAGEM, TIMEOUT_WHATSAPP)
    except TimeoutException:
        raise RuntimeError(
            "Conversa não abriu. WhatsApp deslogado (QR Code) ou número inválido?"
        )
    time.sleep(2)

    # 1) Copia a imagem para a área de transferência
    copiar_imagem(caminho_imagem)

    # 2) Foca a caixa de mensagem da conversa e cola (Ctrl+V).
    #    O WhatsApp abre a pré-visualização da imagem como FOTO.
    focar(driver, caixa)
    ActionChains(driver).key_down(Keys.CONTROL).send_keys("v").key_up(Keys.CONTROL).perform()
    log.info("Imagem colada na conversa (Ctrl+V)")

    # 3) Espera a pré-visualização da imagem abrir
    time.sleep(3)

    # 4) Legenda: digita no campo de legenda da pré-visualização
    #    (se falhar, NÃO interrompe: a imagem é enviada sem legenda)
    campo_legenda = driver.execute_script(JS_ACHAR_LEGENDA)
    if legenda and campo_legenda is not None:
        try:
            digitar_texto(driver, campo_legenda, legenda)
            time.sleep(0.5)
        except Exception as e:
            log.warning(f"Não deu para digitar a legenda ({type(e).__name__}) — seguindo sem")
    elif legenda:
        log.warning("Campo de legenda não encontrado — enviando só a imagem")

    # 5) Envia
    # 5a) Enter na legenda: no WhatsApp, Enter no campo da legenda envia a
    #     imagem. O Enter vai para o elemento com foco (sem clicar em nada).
    if campo_legenda is not None:
        try:
            focar(driver, campo_legenda)
            ActionChains(driver).send_keys(Keys.ENTER).perform()
            log.info("Enter pressionado na legenda")
        except Exception as e:
            log.info(f"Enter na legenda falhou ({type(e).__name__})")
        time.sleep(3)

    # 5b) Se a pré-visualização ainda estiver aberta, clique REAL no botão
    #     (ActionChains move o mouse e clica, como uma pessoa faria; o
    #     clique via JavaScript às vezes é ignorado pelo WhatsApp).
    if previa_aberta(campo_legenda) or campo_legenda is None:
        botao_enviar = None
        fim = time.time() + 15
        while time.time() < fim and not botao_enviar:
            botao_enviar = driver.execute_script(JS_ACHAR_BOTAO_ENVIAR)
            if not botao_enviar:
                time.sleep(1)

        if botao_enviar:
            log.info(f"Clicando em: {driver.execute_script(JS_DESCREVER, botao_enviar)}")
            ActionChains(driver).move_to_element(botao_enviar).pause(0.3).click().perform()
            time.sleep(3)
        else:
            log.warning("Botão Enviar não encontrado")
            log.info(f"Botões visíveis (diagnóstico): {driver.execute_script(JS_DIAGNOSTICO_BOTOES)}")

    # 6) Confirma: a pré-visualização fecha depois do envio
    fim = time.time() + 30
    while time.time() < fim and previa_aberta(campo_legenda):
        time.sleep(1)

    if previa_aberta(campo_legenda):
        # Só AVISA (não gera erro): se gerasse, o main() tentaria de novo e
        # o contato poderia receber a imagem DUAS vezes.
        log.warning("A pré-visualização não fechou — imagem possivelmente NÃO enviada")
        log.info(f"Botões visíveis (diagnóstico): {driver.execute_script(JS_DIAGNOSTICO_BOTOES)}")

    # Dá tempo do upload terminar antes de qualquer outra ação
    time.sleep(5)
    log.info("✅ Bom dia enviado!")


# ======================================================
# PRINCIPAL
# ======================================================

def main():
    parser = argparse.ArgumentParser(description="Bom dia abençoado para o padrinho")
    parser.add_argument("--teste", action="store_true",
                        help="só pesquisa e baixa a imagem, sem enviar")
    args = parser.parse_args()

    log.info("=" * 50)
    log.info(f"Início {'(MODO TESTE)' if args.teste else ''}")

    historico = carregar_historico()
    driver = conectar_chrome()

    # --- Imagem: Google primeiro, reserva se falhar ---
    try:
        imagem = buscar_imagem_google(driver, historico)
    except Exception as e:
        log.warning(f"Google falhou ({e}) — usando imagem reserva")
        imagem = imagem_reserva()
        if not imagem:
            log.error("Sem imagem do Google e sem imagens na pasta reserva")
            return 1

    if args.teste:
        log.info(f"MODO TESTE: imagem pronta em {imagem}, nada foi enviado")
        return 0

    # --- Envio (com 1 nova tentativa se falhar) ---
    for tentativa in (1, 2):
        try:
            enviar_imagem_whatsapp(driver, imagem, LEGENDA)
            salvar_historico(historico)
            return 0
        except Exception as e:
            log.error(f"Tentativa {tentativa} falhou: {type(e).__name__}: {e}")
            if tentativa == 1:
                time.sleep(15)

    # Print da tela para entender o erro
    try:
        driver.save_screenshot(str(PASTA_BASE / f"erro_{datetime.now():%Y-%m-%d}.png"))
    except Exception:
        pass

    # Obs.: não chamamos driver.quit() de propósito em nenhum ponto — isso
    # fecharia o Chrome com o WhatsApp. O Selenium só se desconecta ao terminar.
    return 1


if __name__ == "__main__":
    sys.exit(main())
