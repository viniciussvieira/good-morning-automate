@echo off
REM ======================================================
REM BOM DIA ABENCOADO PARA O PADRINHO
REM
REM Agendar no Agendador de Tarefas do Windows:
REM   1. Agendador de Tarefas ^> Criar Tarefa (nao "Tarefa Basica")
REM   2. Geral: marcar "Executar somente quando o usuario estiver conectado"
REM      (o Chrome precisa de tela; nao funciona com a sessao bloqueada
REM       por "executar estando o usuario conectado ou nao")
REM   3. Disparadores: Diariamente, 06:00
REM   4. Acoes: Iniciar um programa -^> este arquivo .bat
REM   5. Condicoes: marcar "Acordar o computador para executar esta tarefa"
REM   6. Configuracoes: "Executar a tarefa assim que possivel apos uma
REM      inicializacao agendada ser perdida" (se o PC estava desligado as 6h)
REM
REM Teste manual sem enviar: py bom_dia_padrinho.py --teste
REM ======================================================

REM Vai para a pasta deste .bat (funciona de qualquer lugar)
cd /d "%~dp0"

py bom_dia_padrinho.py
exit /b %ERRORLEVEL%
