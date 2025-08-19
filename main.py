import flet as ft
import mysql.connector
import pandas as pd
import math
import os
import subprocess
import sys # Para obter o interpretador Python atual
import xml.etree.ElementTree as ET
import re

#from Excel.xlwings.pro.reports.filters import width

#from Excel.tests.test_active import TestView

XML_DIR = r"\\10.87.199.29\c$\xampp\htdocs\ftp_recebedor\upload_de_dados\planos_triagem_po"
def limpar_rampa(rampa):
    return re.sub(r"^[A-Z]+", "", rampa.strip()).lstrip("0")
# Configurações do banco de dados
db_config = {

    "host": "localhost",
    "user": "root",
    "password": "",
   "database": "sci_planos_triagem",
    "port": 3307
}
def listar_tabelas():
    try:
        conn = mysql.connector.connect(**db_config)
        cursor = conn.cursor()
        cursor.execute("SHOW TABLES")
        #tabelas = [t[0] for t in cursor.fetchall()]
        tabelas = [linha[0] for linha in cursor.fetchall()]
        cursor.close()
        conn.close()
        return tabelas
    except mysql.connector.Error as err:
        return [f"Erro: {err}"]

# Duplicar tabela
def duplicar_tabela(nome_original, nome_novo):
    try:
        conn = mysql.connector.connect(**db_config)
        cursor = conn.cursor()

        # Cria tabela com estrutura e dados
        sql = f"CREATE TABLE `{nome_novo}` AS SELECT * FROM `{nome_original}`"
        cursor.execute(sql)

        conn.commit()
        cursor.close()
        conn.close()
        return f"✅ Tabela '{nome_original}' duplicada como '{nome_novo}'."
    except mysql.connector.Error as err:
        return f"❌ Erro: {err}"
def main(page: ft.Page):


    page.title = "Editor de Banco de Dados"
    page.scroll = ft.ScrollMode.AUTO

    page.bgcolor = '#b8ced1'
    #page.window_bgcolor = '#5ef970'

    dropdown = ft.Dropdown(label=" Selecione a Tabela ", width=250, expand=True,)
    data_table = ft.Column()
    export_button = ft.ElevatedButton(text="Exportar para Excel", disabled=True)
    status = ft.Text(" ")
    paginacao = ft.Row()


    # dados_atuais agora vai guardar dicionários: {'original_data': tuple, 'text_fields': list_of_text_fields, 'id_value': id_of_row}
    dados_atuais = []
    colunas = []
    pagina_atual = 0
    total_paginas = 0
    todos_os_dados = []  # Guarda todos os dados brutos do banco
    dados_para_exibir = []  # Guarda os dados filtrados e paginados para exibição
    registros_por_pagina = 30

############################################################################################
    resultado = ft.Text()

    # Dropdown para selecionar tabela
    dropdown_tabelas = ft.Dropdown(label="Escolha a tabela de origem", options=[])
    input_novo_nome = ft.TextField(label="Nome da nova tabela")

    xml_file_path = ft.Ref[ft.Text]()
    excel_file_path = ft.Ref[ft.Text]()
    results_content = ft.Ref[ft.Column]()

    def listar_arquivos_xml():
        try:
            return sorted([f for f in os.listdir(XML_DIR) if f.lower().endswith(".xml")])
        except FileNotFoundError:
            return []

    todos_xmls = listar_arquivos_xml()

    autocomplete_input = ft.TextField(
        label="Buscar arquivo XML...",
        on_change=lambda e: filtrar_arquivos(e.control.value)
    )

    autocomplete_container = ft.Container(
        content=ft.Column(
            controls=[],
            scroll=ft.ScrollMode.ALWAYS,
            spacing=0,
        ),
        height=400,
        border=ft.border.all(1, ft.colors.GREY_300),
        border_radius=5,
        padding=5,
        visible=False
    )

    def filtrar_arquivos(texto):
        sugestoes = [f for f in todos_xmls if texto.lower() in f.lower()]
        autocomplete_container.content.controls.clear()
        for item_nome in sugestoes:
            autocomplete_container.content.controls.append(
                ft.TextButton(
                    text=item_nome,
                    on_click=lambda e, arquivo=item_nome: selecionar_arquivo(arquivo),
                    style=ft.ButtonStyle(padding=10)
                )
            )
        autocomplete_container.visible = bool(sugestoes)
        page.update()

    def selecionar_arquivo(nome_arquivo):
        caminho = os.path.join(XML_DIR, nome_arquivo)
        xml_file_path.current.value = caminho
        autocomplete_input.value = nome_arquivo
        autocomplete_container.visible = False
        page.update()

    def read_xml_data(file_path):
        tipo_map = {"EN": "Envelope", "EV": "Envelope", "PA": "Pacote", "PD": "Pacote"}
        data_list = []
        try:
            tree = ET.parse(file_path)
            root = tree.getroot()
            namespace_uri = "http://www.correios.com.br/maqTriE"
            full_item_tag_name = f'{{{namespace_uri}}}faixa'

            for item in root.iter(full_item_tag_name):
                cep_ini = item.get('cepInicial')
                cep_fim = item.get('cepFinal')
                tipo = item.get('cdTipoObjeto')
                rampa = item.get('rampaPrincipal')

                if cep_ini and cep_fim and tipo and rampa:
                    tipo_nome = tipo_map.get(tipo.strip(), tipo.strip())
                    data_list.append({
                        "cep_ini": cep_ini.strip().zfill(8),
                        "cep_fim": cep_fim.strip().zfill(8),
                        "tipo": tipo_nome,
                        "rampa": limpar_rampa(rampa)
                    })
            return sorted(data_list, key=lambda x: (x["cep_ini"], x["cep_fim"], x["tipo"]))
        except Exception as e:
            results_content.current.controls.append(
                ft.Text(f"Erro ao ler XML: {e}", color=ft.colors.RED_500))
            page.update()
            return None

    def read_excel_data(file_path):
        data_list = []
        try:
            df = pd.read_excel(file_path)
            df.columns = df.columns.str.strip().str.lower()
            required_cols = ['cep inicial', 'cep final', 'tipo de objeto', 'saída principal']
            if not all(col in df.columns for col in required_cols):
                raise ValueError("Planilha deve conter as colunas: CEP Inicial, CEP Final, Tipo de Objeto, Saída Principal")

            for _, row in df.iterrows():
                try:
                    data_list.append({
                        "cep_ini": str(int(row['cep inicial'])).zfill(8),
                        "cep_fim": str(int(row['cep final'])).zfill(8),
                        "tipo": str(row['tipo de objeto']).strip().title(),
                        "rampa": limpar_rampa(str(row['saída principal']))
                    })
                except:
                    continue
            return sorted(data_list, key=lambda x: (x["cep_ini"], x["cep_fim"], x["tipo"]))
        except Exception as e:
            results_content.current.controls.append(
                ft.Text(f"Erro ao ler Excel: {e}", color=ft.colors.RED_500))
            page.update()
            return None

    def format_faixa(faixa):
        return f"{faixa['cep_ini']} a {faixa['cep_fim']} | Tipo: {faixa['tipo']} | Rampa: {faixa['rampa']}"

    def compare_data(xml_data, excel_data):
        differences = []
        max_len = max(len(xml_data), len(excel_data))

        for i in range(max_len):
            xml_line = xml_data[i] if i < len(xml_data) else None
            excel_line = excel_data[i] if i < len(excel_data) else None

            if xml_line != excel_line:
                diff = f"• Linha {i+1}:\n"
                if xml_line:
                    diff += f"  XML:   {format_faixa(xml_line)}\n"
                else:
                    diff += "  XML:   (linha ausente)\n"
                if excel_line:
                    diff += f"  Excel: {format_faixa(excel_line)}"
                else:
                    diff += "  Excel: (linha ausente)"
                differences.append(diff)

        return differences

    def process_comparison(e):
        results_content.current.controls.clear()
        results_content.current.controls.append(ft.ProgressBar(width=400))
        page.update()

        xml_file = xml_file_path.current.value
        excel_file = excel_file_path.current.value
        if not xml_file or not excel_file:
            results_content.current.controls.clear()
            results_content.current.controls.append(
                ft.Text("Por favor, selecione ambos os arquivos.", color=ft.colors.ORANGE_500))
            page.update()
            return

        xml_data = read_xml_data(xml_file)
        excel_data = read_excel_data(excel_file)

        results_content.current.controls.clear()
        if xml_data is None or excel_data is None:
            return

        differences = compare_data(xml_data, excel_data)
        page.last_differences = differences

        if not differences:
            results_content.current.controls.append(
                ft.Text("✅ Arquivos idênticos!", color=ft.colors.GREEN_700, weight=ft.FontWeight.BOLD))
        else:
            results_content.current.controls.append(
                ft.Text("⚠️ Divergências encontradas:", color=ft.colors.ORANGE_700, weight=ft.FontWeight.BOLD, size=16))
            for diff in differences:
                results_content.current.controls.append(
                    ft.Container(
                        content=ft.Text(diff, color=ft.colors.RED_600),
                        padding=5,
                        margin=ft.margin.symmetric(vertical=2),
                        border_radius=5,
                        border=ft.border.all(1, ft.colors.RED_300)
                    ))
        page.update()

    def export_result_to_txt(e):
        if not hasattr(page, "last_differences") or not page.last_differences:
            results_content.current.controls.append(
                ft.Text("Nenhum resultado para exportar.", color=ft.colors.ORANGE_400))
            page.update()
            return

        file_path = os.path.join(os.getcwd(), "resultado_comparacao.txt")
        with open(file_path, "w", encoding="utf-8") as f:
            for linha in page.last_differences:
                f.write(linha + "\n")

        results_content.current.controls.append(
            ft.Text(f"✅ Exportado: {file_path}", color=ft.colors.GREEN_700))
        page.update()

    def pick_excel_file_result(e: ft.FilePickerResultEvent):
        if e.files:
            excel_file_path.current.value = e.files[0].path
        else:
            excel_file_path.current.value = "Nenhum arquivo Excel selecionado"
        page.update()

    excel_file_picker = ft.FilePicker(on_result=pick_excel_file_result)
    page.overlay.append(excel_file_picker)





    def mostrar_popup(msg):
        dialog = ft.AlertDialog(
            title=ft.Text("Aviso"),
            content=ft.Text(msg),
            #actions=[ft.TextButton("Fechar", on_click=lambda e: dialog.dismiss())],
            actions=[ft.TextButton("Fechar", on_click=lambda e: fechar_dialog())],
            modal=True
        )

        def fechar_dialog():
            dialog.open = False
            page.update()
        page.dialog = dialog
        dialog.open = True
        page.update()


        # Exemplo de uso




    #############################################################################################

    def conectar_banco():
        return mysql.connector.connect(**db_config)

    def ao_carregar(e):
        tabelas = listar_tabelas()
        dropdown_tabelas.options = [ft.dropdown.Option(t) for t in tabelas]
        page.update()

    def ao_duplicar(e):
        origem = dropdown_tabelas.value
        novo_nome = input_novo_nome.value.strip()

        if not origem or not novo_nome:
            resultado.value = "⚠️ Preencha todos os campos."
        else:
            resultado.value = duplicar_tabela(origem, novo_nome)
            ao_carregar(None)
            carregar_tabelas()

        page.update()



    def open_dev_page(e):
        # Constrói o comando para executar page.dev.py como um script Python
        # sys.executable é o caminho para o interpretador Python atual
        # Isso garante que ele use o mesmo ambiente virtual, se houver
        command = [sys.executable, "page.py"]

        try:
            # Inicia o processo em segundo plano
            # Isso abrirá uma nova janela/tab do navegador com a página de desenvolvimento
            subprocess.Popen(command)
            page.snack_bar = ft.SnackBar(
                ft.Text("Página de Desenvolvimento aberta em uma nova janela!"),
                open=True
            )
            page.update()
        except Exception as ex:

            page.overlay.append(
                ft.SnackBar(
                    ft.Text("Página de Desenvolvimento aberta em uma nova janela!"),
                    open=True
                )
            )
            page.update()




    def button_clicked(e):
        #t.value = f"Planos selecionados:  {a1.value}, {b2.value}, {c3.value}, {d4.value}, {c5.value}."
        t.value = f"Planos selecionados:  {c5.value}."
        page.update()

    t = ft.Text()
    #a1 = ft.Checkbox(label="ALA A", value=False)
    #b2 = ft.Checkbox(label="ALA B", value=False)
    #c3 = ft.Checkbox(label="ALA C", value=False)
    #d4 = ft.Checkbox(label="ALA D", value=False)
    c5 = ft.Checkbox(        label="PAC'",        label_position=ft.LabelPosition.LEFT,    )

    c6 = ft.Checkbox(        label="SEDEX'",        label_position=ft.LabelPosition.LEFT,    )


    E1 = ft.Checkbox(label="E1", value=False)
    I1 = ft.Checkbox(label="I1", value=False)
    J1 = ft.Checkbox(label="J1", value=False)
    K1 = ft.Checkbox(label="K1", value=False)
    K2 = ft.Checkbox(label="K2", value=False)
    L1 = ft.Checkbox(label="L1", value=False)
    L2 = ft.Checkbox(label="L2", value=False)
    M1 = ft.Checkbox(label="M1", value=False)
    N1 = ft.Checkbox(label="N1", value=False)
    O1 = ft.Checkbox(label="O1", value=False)
    P1 = ft.Checkbox(label="P1", value=False)
    S1 = ft.Checkbox(label="S1", value=False)
    T1 = ft.Checkbox(label="T1", value=False)
    SRO = ft.Checkbox(label="SRO", value=False)
    SEDEX = ft.Checkbox(label="SEDEX", value=False)
    PAC = ft.Checkbox(label="PAC", value=False)
    Envelope = ft.Checkbox(label="Envelope", value=False)
    Pacote = ft.Checkbox(label="Pacote", value=False)


    registros_por_pagina_dropdown = ft.Dropdown(
        label=" Itens por página ",
        value=str(registros_por_pagina),
        options=[ft.dropdown.Option(str(n)) for n in [0, 10, 20, 30, 50, 100, 150,200,400]],
        width=180,

    )
    # NOVA FUNÇÃO: Salvar alterações no banco de dados
    def salvar_alteracoes(e):
        nonlocal todos_os_dados
        nome_tabela = dropdown.value
        if not nome_tabela:
            status.value = "Selecione uma tabela para salvar alterações."
            page.update()
            return

        updates_feitos = 0
        try:
            conn = conectar_banco()
            cursor = conn.cursor()

            coluna_id = "id"  # Assume que 'id' é a chave primária
            coluna_id_idx = colunas.index(coluna_id)  # Índice da coluna ID

            for linha_data in dados_atuais:
                original_tuple = linha_data['original_data']
                current_text_fields = linha_data['text_fields']
                row_id = linha_data['id_value']

                # Lista de colunas que foram alteradas e seus novos valores
                alteracoes_para_update = {}

                for col_idx, tf in enumerate(current_text_fields):
                    original_value = str(original_tuple[col_idx] if original_tuple[col_idx] is not None else '')
                    current_value = tf.value

                    # Converte o valor de volta para o tipo original se possível para comparação e update
                    # Essa parte é crucial e pode precisar de ajustes dependendo dos tipos das suas colunas
                    col_name = colunas[col_idx]

                    # Ignorar a coluna 'id' para UPDATE, pois ela é a chave primária
                    if col_name == coluna_id:
                        continue

                    # Tentativa de conversão de tipo para comparação precisa e para o UPDATE
                    # Isso é um exemplo, pode precisar de mais tipos (float, datetime, etc.)
                    try:
                        if isinstance(original_tuple[col_idx], int):
                            converted_current_value = int(current_value) if current_value else None
                        elif isinstance(original_tuple[col_idx], float):
                            converted_current_value = float(current_value) if current_value else None
                        else:  # Para varchar, text, etc.
                            converted_current_value = current_value if current_value != '' else None
                    except (ValueError, TypeError):
                        # Em caso de erro de conversão, use o valor string bruto ou None
                        converted_current_value = current_value if current_value != '' else None

                    # Compara o valor original com o valor atual do TextField (após possível conversão)
                    if converted_current_value != original_tuple[col_idx]:
                        alteracoes_para_update[col_name] = converted_current_value

                if alteracoes_para_update:
                    # Constrói a parte SET da query UPDATE
                    set_clauses = ", ".join([f"{col} = %s" for col in alteracoes_para_update.keys()])
                    values_to_update = list(alteracoes_para_update.values())

                    query = f"UPDATE {nome_tabela} SET {set_clauses} WHERE {coluna_id} = %s"
                    params = tuple(values_to_update + [row_id])

                    print(f"DEBUG: Executando UPDATE: {query} com params: {params}")
                    cursor.execute(query, params)
                    updates_feitos += cursor.rowcount  # Conta as linhas afetadas

            conn.commit()
            conn.close()

            if updates_feitos > 0:
                status.value = f"{updates_feitos} registro(s) atualizado(s) com sucesso!"
                page.snack_bar = ft.SnackBar(ft.Text("Alterações salvas com sucesso!", color=ft.colors.WHITE),
                                             bgcolor=ft.colors.BLUE_800, open=True, duration=3000)
                recarregar_todos_os_dados()  # Recarrega para refletir as alterações salvas
                aplicar_filtro_interno()  # Re-aplica filtro e re-exibe a página
            else:
                status.value = "Nenhuma alteração foi detectada para salvar."
                page.snack_bar = ft.SnackBar(ft.Text("Nenhuma alteração detectada.", color=ft.colors.YELLOW_800),
                                             bgcolor=ft.colors.YELLOW_200, open=True, duration=2000)

        except Exception as ex:
            status.value = f"Erro ao salvar alterações: {ex}"
            page.snack_bar = ft.SnackBar(ft.Text(f"Erro ao salvar: {ex}", color=ft.colors.WHITE),
                                         bgcolor=ft.colors.RED_700, open=True, duration=5000)
        page.update()

    filtro_campo = ft.TextField(label="Buscar SRO",width=100, )
    filtro_rampa = ft.TextField(label="Buscar Rampa", width=100,)
    filtro_tipo_objeto = ft.TextField(label="Buscar Tipo Objeto", width=150)

    filtro_botao = ft.ElevatedButton(text="Buscar", icon=ft.icons.SEARCH, color="#0a0a0a")
    export_colunas_button = ft.ElevatedButton(
        text="Exportar para o CAUT",
        disabled=True,
        icon=ft.icons.DOWNLOAD_FOR_OFFLINE,

    )
    conferiri_cep_button = ft.ElevatedButton(
        text="Conferir CEP",
        disabled=True,
        icon=ft.icons.DOWNLOAD_FOR_OFFLINE,

    )
    # NOVO BOTÃO: Salvar Alterações
    salvar_button = ft.ElevatedButton(
        text="Salvar Alterações",
        icon=ft.icons.SAVE,
        on_click=salvar_alteracoes,
        disabled=True,  # Começa desabilitado, habilita quando a tabela é carregada
        style=ft.ButtonStyle(bgcolor=ft.colors.BLUE_700, color=ft.colors.WHITE)
    )




    def carregar_tabelas():
        try:
            conn = conectar_banco()
            cursor = conn.cursor()
            cursor.execute("SHOW TABLES")
            tabelas = [linha[0] for linha in cursor.fetchall()]
            dropdown.options = [ft.dropdown.Option(t) for t in tabelas]
            page.update()

            conn.close()


        except Exception as e:
            status.value = f"Erro: {e}"

            page.update()

    # Duplicar tabela
    def duplicar_tabela(nome_original, nome_novo):
        try:
            conn = conectar_banco()
            cursor = conn.cursor()

            # Cria tabela com estrutura e dados
            sql = f"CREATE TABLE `{nome_novo}` AS SELECT * FROM `{nome_original}`"
            cursor.execute(sql)

            conn.commit()
            cursor.close()
            conn.close()
            return f"✅ Tabela '{nome_original}' duplicada como '{nome_novo}'."
        except mysql.connector.Error as err:
            return f"❌ Erro: {err}"
    # NOVA FUNÇÃO: Recarrega todos os dados brutos do banco


    def recarregar_todos_os_dados():
        nonlocal todos_os_dados, colunas
        nome_tabela = dropdown.value
        if not nome_tabela:
            todos_os_dados = []
            colunas = []
            return

        conn = conectar_banco()
        cursor = conn.cursor()

        # Opcional: Adicionar ORDER BY aqui se desejar que os dados venham ordenados do banco
        # order_by_column = "sro" # Exemplo: "sro" ou "id"
        # try:
        #     cursor.execute(f"SELECT * FROM {nome_tabela} ORDER BY {order_by_column} ASC")
        # except mysql.connector.Error as err:
        #     print(f"Erro ao ordenar por '{order_by_column}': {err}. Carregando sem ordenação.")
        cursor.execute(f"SELECT * FROM {nome_tabela}")  # Consulta padrão sem ORDER BY

        colunas = [desc[0] for desc in cursor.description]
        todos_os_dados = cursor.fetchall()
        conn.close()

    # Função principal para carregar dados e exibir
    def carregar_dados(e=None):
        nonlocal dados_atuais, total_paginas, pagina_atual, registros_por_pagina, dados_para_exibir

        recarregar_todos_os_dados()  # Sempre começa recarregando todos os dados brutos

        aplicar_filtro_interno()  # Aplica o filtro atual (ou nenhum filtro) e atualiza a exibição

        export_button.disabled = False
        export_colunas_button.disabled = False
        salvar_button.disabled = False  # Habilita o botão salvar quando os dados são carregados
        status.value = f"{len(dados_para_exibir)} registros carregados da tabela '{dropdown.value}'"
        page.update()

    # FUNÇÃO ALTERADA: mostrar_pagina
    def mostrar_pagina(indice_pagina):
        nonlocal dados_atuais, pagina_atual, registros_por_pagina, dados_para_exibir
        pagina_atual = indice_pagina
        data_table.controls.clear()
        dados_atuais.clear()  # Limpa para preencher com as novas linhas da página

        cabecalho = ft.Row([
            ft.Text("Ações", weight=ft.FontWeight.BOLD, width=150),
            *[ft.Text(col, weight=ft.FontWeight.BOLD, width=150) for col in colunas]
        ])
        data_table.controls.append(cabecalho)

        inicio = indice_pagina * registros_por_pagina
        fim = inicio + registros_por_pagina
        dados_da_pagina = dados_para_exibir[inicio:fim]

        if not dados_da_pagina and pagina_atual > 0:
            mostrar_pagina(pagina_atual - 1)
            return

        try:
            coluna_id_idx = colunas.index("id")
        except ValueError:
            coluna_id_idx = 0
            print("Aviso: Coluna 'id' não encontrada. Usando a primeira coluna como ID.")

        for i, linha_tuple_original in enumerate(dados_da_pagina):
            id_do_registro = linha_tuple_original[coluna_id_idx]

            # Lista para armazenar os TextField de cada linha
            text_fields_da_linha = []
            entradas_ui = []

            for campo_idx, campo_valor_original in enumerate(linha_tuple_original):
                tf = ft.TextField(
                    value=str(campo_valor_original if campo_valor_original is not None else ''),
                    width=150,
                    # Adiciona uma referência ao ID e índice da coluna para fácil acesso
                    data={'row_id': id_do_registro, 'col_idx': campo_idx}
                )
                text_fields_da_linha.append(tf)
                entradas_ui.append(tf)

            # Armazena a tupla original e os TextFields desta linha
            dados_atuais.append({
                'original_data': linha_tuple_original,
                'text_fields': text_fields_da_linha,
                'id_value': id_do_registro
            })

            botoes_acao = ft.Row([
                ft.IconButton(
                    icon=ft.icons.DELETE,
                    icon_color="red",
                    tooltip=f"Deletar registro ID: {id_do_registro}",
                    data=id_do_registro,
                    on_click=confirmar_delecao
                ),
                ft.IconButton(
                    icon=ft.icons.CONTENT_COPY,
                    icon_color="blue",
                    tooltip=f"Duplicar registro ID: {id_do_registro}",
                    data=linha_tuple_original,
                    on_click=confirmar_duplicacao
                )
            ], width=150)

            linha_completa = ft.Row([botoes_acao] + entradas_ui)
            data_table.controls.append(linha_completa)

        atualizar_paginacao()
        page.update()

    # NOVA FUNÇÃO: Salvar alterações no banco de dados
    def salvar_alteracoes(e):
        nonlocal todos_os_dados
        nome_tabela = dropdown.value
        if not nome_tabela:
            status.value = "Selecione uma tabela para salvar alterações."
            page.update()
            return

        updates_feitos = 0
        try:
            conn = conectar_banco()
            cursor = conn.cursor()

            coluna_id = "id"  # Assume que 'id' é a chave primária
            coluna_id_idx = colunas.index(coluna_id)  # Índice da coluna ID

            for linha_data in dados_atuais:
                original_tuple = linha_data['original_data']
                current_text_fields = linha_data['text_fields']
                row_id = linha_data['id_value']

                # Lista de colunas que foram alteradas e seus novos valores
                alteracoes_para_update = {}

                for col_idx, tf in enumerate(current_text_fields):
                    original_value = str(original_tuple[col_idx] if original_tuple[col_idx] is not None else '')
                    current_value = tf.value

                    # Converte o valor de volta para o tipo original se possível para comparação e update
                    # Essa parte é crucial e pode precisar de ajustes dependendo dos tipos das suas colunas
                    col_name = colunas[col_idx]

                    # Ignorar a coluna 'id' para UPDATE, pois ela é a chave primária
                    if col_name == coluna_id:
                        continue

                    # Tentativa de conversão de tipo para comparação precisa e para o UPDATE
                    # Isso é um exemplo, pode precisar de mais tipos (float, datetime, etc.)
                    try:
                        if isinstance(original_tuple[col_idx], int):
                            converted_current_value = int(current_value) if current_value else None
                        elif isinstance(original_tuple[col_idx], float):
                            converted_current_value = float(current_value) if current_value else None
                        else:  # Para varchar, text, etc.
                            converted_current_value = current_value if current_value != '' else None
                    except (ValueError, TypeError):
                        # Em caso de erro de conversão, use o valor string bruto ou None
                        converted_current_value = current_value if current_value != '' else None

                    # Compara o valor original com o valor atual do TextField (após possível conversão)
                    if converted_current_value != original_tuple[col_idx]:
                        alteracoes_para_update[col_name] = converted_current_value

                if alteracoes_para_update:
                    # Constrói a parte SET da query UPDATE
                    set_clauses = ", ".join([f"{col} = %s" for col in alteracoes_para_update.keys()])
                    values_to_update = list(alteracoes_para_update.values())

                    query = f"UPDATE {nome_tabela} SET {set_clauses} WHERE {coluna_id} = %s"
                    params = tuple(values_to_update + [row_id])

                    print(f"DEBUG: Executando UPDATE: {query} com params: {params}")
                    cursor.execute(query, params)
                    updates_feitos += cursor.rowcount  # Conta as linhas afetadas

            conn.commit()
            conn.close()

            if updates_feitos > 0:
                status.value = f"{updates_feitos} registro(s) atualizado(s) com sucesso!"
                page.snack_bar = ft.SnackBar(ft.Text("Alterações salvas com sucesso!", color=ft.colors.WHITE),
                                             bgcolor=ft.colors.BLUE_800, open=True, duration=3000)
                recarregar_todos_os_dados()  # Recarrega para refletir as alterações salvas
                aplicar_filtro_interno()  # Re-aplica filtro e re-exibe a página
            else:
                status.value = "Nenhuma alteração foi detectada para salvar."
                page.snack_bar = ft.SnackBar(ft.Text("Nenhuma alteração detectada.", color=ft.colors.YELLOW_800),
                                             bgcolor=ft.colors.YELLOW_200, open=True, duration=2000)

        except Exception as ex:
            status.value = f"Erro ao salvar alterações: {ex}"
            page.snack_bar = ft.SnackBar(ft.Text(f"Erro ao salvar: {ex}", color=ft.colors.WHITE),
                                         bgcolor=ft.colors.RED_700, open=True, duration=5000)
        page.update()

    # Nova função para confirmar a deleção
    def confirmar_delecao(e):
        id_para_deletar = e.control.data

        dialogo_confirmacao = ft.AlertDialog(
            modal=True,
            title=ft.Text("Confirmar Deleção"),
            content=ft.Text(f"Tem certeza que deseja apagar o registro com ID: {id_para_deletar}?"),
            actions=[
                ft.TextButton("Cancelar", on_click=lambda event: fechar_dialogo(event, confirmar=False)),
                ft.FilledButton("Apagar", on_click=lambda event: fechar_dialogo(event, confirmar=True,id_registro=id_para_deletar),
                                style=ft.ButtonStyle(bgcolor=ft.colors.RED_600)),
            ],
            actions_alignment=ft.MainAxisAlignment.END,
            on_dismiss=lambda e: print("Diálogo de confirmação de deleção descartado!"),
        )

        page.dialog = dialogo_confirmacao
        dialogo_confirmacao.open = True
        page.update()

    # Função para fechar o diálogo de deleção e decidir se deleta
    def fechar_dialogo(e, confirmar: bool, id_registro=None):
        page.dialog.open = False
        page.update()
        if confirmar and id_registro is not None:
            deletar_linha(id_registro)  # Chama a função de deleção passando o ID

    # FUNÇÃO ALTERADA: deletar_linha (sempre recebe o ID, não o evento)
    def deletar_linha(id_registro_a_deletar):
        nonlocal todos_os_dados, dados_para_exibir

        nome_tabela = dropdown.value
        coluna_id = "id"  # Assume que 'id' é a coluna da chave primária

        try:
            conn = conectar_banco()
            cursor = conn.cursor()
            query = f"DELETE FROM {nome_tabela} WHERE {coluna_id} = %s"
            cursor.execute(query, (id_registro_a_deletar,))

            linhas_afetadas = cursor.rowcount
            print(f"DEBUG: {linhas_afetadas} linhas afetadas pela deleção para o ID: {id_registro_a_deletar}.")

            conn.commit()
            conn.close()

            recarregar_todos_os_dados()
            aplicar_filtro_interno()

            status.value = f"Registro deletado com sucesso! ({linhas_afetadas} linha(s) removida(s))"
            page.snack_bar = ft.SnackBar(ft.Text("Registro deletado com sucesso!", color=ft.colors.WHITE),
                                         bgcolor=ft.colors.GREEN, open=True, duration=5000)
        except Exception as e:
            status.value = f"Erro ao deletar registro: {e}"
            page.snack_bar = ft.SnackBar(ft.Text(f"Erro: {e}", color=ft.colors.WHITE), bgcolor=ft.colors.RED, open=True,
                                         duration=3000)
        page.update()

    # NOVA FUNÇÃO: Confirmar Duplicação
    def confirmar_duplicacao(e):
        registro_para_duplicar = e.control.data  # Pega a tupla do registro do atributo 'data' do botão

        # Encontra o ID para exibir no pop-up (assumindo que 'id' é a chave primária)
        try:
            coluna_id_idx = colunas.index("id")
            id_do_registro = registro_para_duplicar[coluna_id_idx]
        except ValueError:
            id_do_registro = "N/A"  # Caso não encontre a coluna 'id'

        detalhes_registro = f"ID: {id_do_registro}"
        if "sro" in colunas:
            detalhes_registro += f", SRO: {registro_para_duplicar[colunas.index('sro')]}"

        if "direcao" in colunas:
            detalhes_registro += f", DIREÇÃO: {registro_para_duplicar[colunas.index('direcao')]}"

        dialogo_confirmacao_duplicar = ft.AlertDialog(
            modal=True,
            title=ft.Text("Confirmar Duplicação"),
            content=ft.Text(f"Tem certeza que deseja duplicar o registro:\n{detalhes_registro}?"),
            actions=[
                ft.TextButton("Cancelar", on_click=lambda event: fechar_dialogo_duplicar(event, confirmar=False)),
                ft.FilledButton("Duplicar", on_click=lambda event: fechar_dialogo_duplicar(event, confirmar=True,
                                                                                           registro=registro_para_duplicar),
                                style=ft.ButtonStyle(bgcolor=ft.colors.BLUE_600)),
            ],
            actions_alignment=ft.MainAxisAlignment.END,
            on_dismiss=lambda e: print("Diálogo de confirmação de duplicação descartado!"),
        )

        page.dialog = dialogo_confirmacao_duplicar
        dialogo_confirmacao_duplicar.open = True
        page.update()

    # NOVA FUNÇÃO: Fechar Diálogo de Duplicação
    def fechar_dialogo_duplicar(e, confirmar: bool, registro=None):
        page.dialog.open = False
        page.update()
        if confirmar and registro is not None:
            duplicar_linha(registro)  # Chama a função de duplicação passando a tupla do registro

    # FUNÇÃO ALTERADA: duplicar_linha (agora sempre recebe a tupla do registro, não o evento)
    def duplicar_linha(registro_a_duplicar):
        nome_tabela = dropdown.value
        # A coluna 'id' não deve ser incluída na inserção se for AUTO_INCREMENT
        colunas_insert = [col for col in colunas if col != 'id']

        # Pega os valores do registro, excluindo o 'id'
        dados_a_inserir = [registro_a_duplicar[colunas.index(col)] for col in colunas_insert]

        placeholders = ", ".join(["%s"] * len(dados_a_inserir))
        colunas_str = ", ".join(colunas_insert)

        try:
            conn = conectar_banco()
            cursor = conn.cursor()
            query = f"INSERT INTO {nome_tabela} ({colunas_str}) VALUES ({placeholders})"
            cursor.execute(query, tuple(dados_a_inserir))
            conn.commit()
            conn.close()

            recarregar_todos_os_dados()
            aplicar_filtro_interno()

            status.value = "Registro duplicado com sucesso!"
            page.snack_bar = ft.SnackBar(ft.Text("Registro duplicado com sucesso!", color=ft.colors.WHITE),
                                         bgcolor=ft.colors.GREEN, open=True, duration=2000)
        except Exception as e:
            status.value = f"Erro ao duplicar registro: {e}"
            page.snack_bar = ft.SnackBar(ft.Text(f"Erro: {e}", color=ft.colors.WHITE), bgcolor=ft.colors.RED, open=True,
                                         duration=3000)
        page.update()

    def atualizar_paginacao():
        nonlocal total_paginas
        total_paginas = math.ceil(len(dados_para_exibir) / registros_por_pagina)
        paginacao.controls.clear()

        botao_anterior = ft.ElevatedButton(text="Anterior", on_click=lambda e: mostrar_pagina(pagina_atual - 1),
                                           disabled=pagina_atual == 0)
        botao_proximo = ft.ElevatedButton(text="Próxima", on_click=lambda e: mostrar_pagina(pagina_atual + 1),
                                          disabled=pagina_atual >= total_paginas - 1)

        paginacao.controls.extend(
            [botao_anterior, ft.Text(f"Página {pagina_atual + 1} de {total_paginas}"), botao_proximo])
        page.update()


    def exportar_para_excel(e):
        nome_tabela = dropdown.value
        if not nome_tabela or not dados_para_exibir:
            return
        df = pd.DataFrame(dados_para_exibir, columns=colunas)
        # dropna tira linhas vazias
        df = df.dropna()
        df.to_excel(f"{nome_tabela}_exportado_filtrado.xlsx", index=False)
        status.value = f"Tabela '{nome_tabela}' (filtrada) exportada para Excel com sucesso!"
        page.update()

    def on_registros_por_pagina_change(e):
        nonlocal registros_por_pagina, total_paginas, pagina_atual
        registros_por_pagina = int(e.control.value)
        total_paginas = math.ceil(len(dados_para_exibir) / registros_por_pagina)
        pagina_atual = 0
        mostrar_pagina(pagina_atual)
        status.value = f"Exibindo {registros_por_pagina} registros por página."
        page.update()

    def deletar_tabela(nome_original):
        try:
            conn = conectar_banco()
            cursor = conn.cursor()
            sql = f"DROP TABLE `{nome_original}`"
            cursor.execute(sql)
            conn.commit()
            cursor.close()
            conn.close()
            return f"✅ Tabela '{nome_original}' deletada com sucesso."
        except mysql.connector.Error as err:
            return f"❌ Erro ao deletar: {err}"
    def ao_deletar_tabela(e):
        origem = dropdown_tabelas.value
        if origem:
            resultado.value = deletar_tabela(origem)
            ao_carregar(None)
        else:
            resultado.value = "Tabela não selecionada."
        page.update()
    def aplicar_filtro_interno():
        nonlocal dados_para_exibir, total_paginas, pagina_atual
        termo_sro = filtro_campo.value.lower().strip()
        termo_rampa = filtro_rampa.value.lower().strip()
        termo_tipo_objeto = filtro_tipo_objeto.value.lower().strip()

        dados_filtrados = []

        for linha in todos_os_dados:
            sro_match = True
            rampa_match = True
            tipo_objeto_match = True

            # Filtro SRO (apenas se preenchido)
            if termo_sro:
                sro_match = any(
                    termo_sro in str(campo).lower()
                    for idx, campo in enumerate(linha)
                    if colunas[idx].lower() == "sro"
                )

            # Filtro Rampa (apenas se preenchido)
            if termo_rampa:
                rampa_match = any(
                    termo_rampa in str(campo).lower()
                    for idx, campo in enumerate(linha)
                    if colunas[idx].lower() == "rampa"
                )

            # Filtro Tipo Objeto (apenas se preenchido)
            if termo_tipo_objeto:
                tipo_objeto_match = any(
                    termo_tipo_objeto in str(campo).lower()
                    for idx, campo in enumerate(linha)
                    if colunas[idx].lower() == "tipo_objeto"
                )

            # Só adiciona a linha se ela passar em todos os filtros preenchidos
            if sro_match and rampa_match and tipo_objeto_match:
                dados_filtrados.append(linha)

        dados_para_exibir = dados_filtrados
        status.value = f"Filtro aplicado: {len(dados_para_exibir)} registros encontrados."

        total_paginas = math.ceil(len(dados_para_exibir) / registros_por_pagina)
        pagina_atual = 0
        mostrar_pagina(pagina_atual)
        export_button.disabled = not bool(dados_para_exibir)
        export_colunas_button.disabled = not bool(dados_para_exibir)
        page.update()

    def aplicar_filtro(e):
        aplicar_filtro_interno()

    def exportar_colunas_especificas(e):
        nome_tabela = dropdown.value
        if not nome_tabela or not todos_os_dados:
            status.value = "Nenhum dado na tabela para exportar as colunas específicas."
            page.update()
            return

        colunas_desejadas_db = ["tipo_objeto", "cepin", "cepfin", "saida_principal", "saida_alternativa", "sro","direcao"]
        nomes_excel_header = {
            "tipo_objeto": "Tipo de Objeto",
            "cepin": "CEP Inicial",
            "cepfin": "CEP Final",
            "saida_principal": "Saída Principal",
            "saida_alternativa": "Saída Alternativa",
            "sro": "Código",
            "direcao": "Direção de triagem",

        }

        dados_para_exportar_selecionado = []
        colunas_presentes_e_desejadas = []
        col_name_to_index = {name: index for index, name in enumerate(colunas)}

        for col_db_name in colunas_desejadas_db:
            if col_db_name in col_name_to_index:
                colunas_presentes_e_desejadas.append(col_db_name)

        if not colunas_presentes_e_desejadas:
            status.value = "Nenhuma das colunas selecionadas foi encontrada na tabela atual para exportar."
            page.update()
            return

        for row_tuple in todos_os_dados:
            new_row_data = [row_tuple[col_name_to_index[col]] for col in colunas_presentes_e_desejadas]
            dados_para_exportar_selecionado.append(new_row_data)

        try:
            df = pd.DataFrame(dados_para_exportar_selecionado,
                              columns=[nomes_excel_header.get(col, col) for col in colunas_presentes_e_desejadas])
            # Filtra somente a coluba que contém -
            df = df[df["Tipo de Objeto"].str.contains("Envelope", case=False, na=False)]
            df = df.dropna()
            df["CEP Final"] = pd.to_numeric(df["CEP Final"].str.replace("-", ""), errors='coerce')

            df["CEP Inicial"] = pd.to_numeric(df["CEP Inicial"].str.replace("-", ""), errors='coerce')

            df = df.dropna(subset=["CEP Inicial", "CEP Final"])
            df = df.sort_values(by="CEP Inicial")

            gaps = []
            for i in range(len(df) - 1):
                atual_fim = int(df.iloc[i]["CEP Final"])
                proximo_inicio = int(df.iloc[i + 1]["CEP Inicial"])
                if atual_fim + 1 < proximo_inicio:
                    gaps.append((atual_fim + 1, proximo_inicio - 1))

            if gaps:
                gaps_formatados = [f"- {str(inicio).zfill(8)} até {str(fim).zfill(8)}" for inicio, fim in gaps]
                mensagem = "⚠️ Lacunas encontradas entre os intervalos de CEP:\n" + "\n".join(gaps_formatados)
                mostrar_popup(mensagem)
                print("⚠️ Lacunas encontradas entre os intervalos de CEP:\n" )
                #status.value = "⚠️ Lacunas encontradas entre os intervalos de CEP:\n" + \
                 #              "\n".join([f"- {inicio} até {fim}" for inicio, fim in gaps])
            else:
                print("⚠️ Lacunas NÂO encontradas entre os intervalos de CEP:\n")
                status.value = "✅ Todos os intervalos de CEP estão conectados, sem lacunas."

            # Reformatar como string com zeros à esquerda

            df["CEP Inicial"] = df["CEP Inicial"].astype(int).astype(str).str.zfill(8)
            df["CEP Final"] = df["CEP Final"].astype(int).astype(str).str.zfill(8)

            file_path = os.path.join(os.path.expanduser('~'), 'Downloads', f"{nome_tabela}_caut_exportado.xlsx")
            df.to_excel(file_path, index=False)
            status.value = f"Colunas específicas da tabela '{nome_tabela}' exportadas para '{file_path}' com sucesso!"
            page.snack_bar = ft.SnackBar(
                ft.Text(f"Exportado (colunas específicas) para: {file_path}", color=ft.colors.WHITE),
                bgcolor=ft.colors.ORANGE_700, open=True, duration=5000)
            page.update()
        except Exception as ex:
            status.value = f"Erro ao exportar colunas específicas para Excel: {ex}"
            page.update()

    def verificador_ceps(e):
        nome_tabela = dropdown.value
        if not nome_tabela or not todos_os_dados:
            status.value = "Nenhum dado na tabela para exportar as colunas específicas."
            page.update()
            return

        colunas_desejadas_db = ["tipo_objeto", "cepin", "cepfin", "saida_principal", "saida_alternativa", "sro","direcao"]
        nomes_excel_header = {
            "tipo_objeto": "Tipo de Objeto",
            "cepin": "CEP Inicial",
            "cepfin": "CEP Final",
            "saida_principal": "Saída Principal",
            "saida_alternativa": "Saída Alternativa",
            "sro": "Código",
            "direcao": "Direção de triagem",

        }

        dados_para_exportar_selecionado = []
        colunas_presentes_e_desejadas = []
        col_name_to_index = {name: index for index, name in enumerate(colunas)}

        for col_db_name in colunas_desejadas_db:
            if col_db_name in col_name_to_index:
                colunas_presentes_e_desejadas.append(col_db_name)

        if not colunas_presentes_e_desejadas:
            status.value = "Nenhuma das colunas selecionadas foi encontrada na tabela atual para exportar."
            page.update()
            return

        for row_tuple in todos_os_dados:
            new_row_data = [row_tuple[col_name_to_index[col]] for col in colunas_presentes_e_desejadas]
            dados_para_exportar_selecionado.append(new_row_data)

        try:
            df = pd.DataFrame(dados_para_exportar_selecionado,
                              columns=[nomes_excel_header.get(col, col) for col in colunas_presentes_e_desejadas])
            # Filtra somente a coluba que contém -
            df = df[df["Tipo de Objeto"].str.contains("Envelope", case=False, na=False)]
            df = df.dropna()
            df["CEP Final"] = pd.to_numeric(df["CEP Final"].str.replace("-", ""), errors='coerce')

            df["CEP Inicial"] = pd.to_numeric(df["CEP Inicial"].str.replace("-", ""), errors='coerce')

            df = df.dropna(subset=["CEP Inicial", "CEP Final"])
            df = df.sort_values(by="CEP Inicial")

            gaps = []
            for i in range(len(df) - 1):
                atual_fim = int(df.iloc[i]["CEP Final"])
                proximo_inicio = int(df.iloc[i + 1]["CEP Inicial"])
                if atual_fim + 1 < proximo_inicio:
                    gaps.append((atual_fim + 1, proximo_inicio - 1))

            if gaps:

                gaps_formatados = [f"- {str(inicio).zfill(8)} até {str(fim).zfill(8)}" for inicio, fim in gaps]
                mensagem = "⚠️ Lacunas encontradas entre os intervalos de CEP:\n" + "\n".join(gaps_formatados)
                mostrar_popup(mensagem)
                print("⚠️ Lacunas encontradas entre os intervalos de CEP:\n")

                #print("⚠️ Lacunas encontradas entre os intervalos de CEP:\n" )
                #status.value = "⚠️ Lacunas encontradas entre os intervalos de CEP:\n" + \
                 #              "\n".join([f"- {inicio} até {fim}" for inicio, fim in gaps])
                #mostrar_popup("⚠️ Lacunas encontradas entre os intervalos de CEP:\n" +  "\n".join([f"- {inicio} até {fim}" for inicio, fim in gaps]))
            else:
                print("⚠✅ Lacunas NÂO encontradas entre os intervalos de CEP:\n")
                status.value = "✅ Todos os intervalos de CEP estão conectados, sem lacunas."

                mensagem = "✅ Lacunas não encontradas entre os intervalos de"
                mostrar_popup(mensagem)

            # Reformatar como string com zeros à esquerda

            df["CEP Inicial"] = df["CEP Inicial"].astype(int).astype(str).str.zfill(8)
            df["CEP Final"] = df["CEP Final"].astype(int).astype(str).str.zfill(8)

        except Exception as ex:
            status.value = f"Erro ao exportar colunas específicas para Excel: {ex}"
            page.update()

    # def verificador_ceps(e):
    #     nome_tabela = dropdown.value
    #     if not nome_tabela or not todos_os_dados:
    #         status.value = "Nenhum dado na tabela para exportar as colunas específicas."
    #         page.update()
    #         return
    #
    #     colunas_desejadas_db = ["tipo_objeto", "cepin", "cepfin", "saida_principal", "saida_alternativa", "sro",
    #                             "direcao"]
    #     nomes_excel_header = {
    #         "tipo_objeto": "Tipo de Objeto",
    #         "cepin": "CEP Inicial",
    #         "cepfin": "CEP Final",
    #         "saida_principal": "Saída Principal",
    #         "saida_alternativa": "Saída Alternativa",
    #         "sro": "Código",
    #         "direcao": "Direção de triagem",
    #     }
    #
    #     dados_para_exportar_selecionado = []
    #     colunas_presentes_e_desejadas = []
    #     col_name_to_index = {name: index for index, name in enumerate(colunas)}
    #
    #     for col_db_name in colunas_desejadas_db:
    #         if col_db_name in col_name_to_index:
    #             colunas_presentes_e_desejadas.append(col_db_name)
    #
    #     if not colunas_presentes_e_desejadas:
    #         status.value = "Nenhuma das colunas selecionadas foi encontrada na tabela atual para exportar."
    #         page.update()
    #         return
    #
    #     for row_tuple in todos_os_dados:
    #         new_row_data = [row_tuple[col_name_to_index[col]] for col in colunas_presentes_e_desejadas]
    #         dados_para_exportar_selecionado.append(new_row_data)
    #
    #     def verificar_lacunas_por_tipo(tipo_objeto):
    #         df = pd.DataFrame(dados_para_exportar_selecionado,
    #                           columns=[nomes_excel_header.get(col, col) for col in colunas_presentes_e_desejadas])
    #         df = df[df["Tipo de Objeto"].str.contains(tipo_objeto, case=False, na=False)]
    #         df = df.dropna()
    #         df["CEP Final"] = pd.to_numeric(df["CEP Final"].str.replace("-", ""), errors='coerce')
    #         df["CEP Inicial"] = pd.to_numeric(df["CEP Inicial"].str.replace("-", ""), errors='coerce')
    #         df = df.dropna(subset=["CEP Inicial", "CEP Final"])
    #         df = df.sort_values(by="CEP Inicial")
    #
    #         gaps = []
    #         for i in range(len(df) - 1):
    #             atual_fim = int(df.iloc[i]["CEP Final"])
    #             proximo_inicio = int(df.iloc[i + 1]["CEP Inicial"])
    #             if atual_fim + 1 < proximo_inicio:
    #                 gaps.append((atual_fim + 1, proximo_inicio - 1))
    #
    #         df["CEP Inicial"] = df["CEP Inicial"].astype(int).astype(str).str.zfill(8)
    #         df["CEP Final"] = df["CEP Final"].astype(int).astype(str).str.zfill(8)
    #
    #         if gaps:
    #             gaps_formatados = [f"- {str(inicio).zfill(8)} até {str(fim).zfill(8)}" for inicio, fim in gaps]
    #             mensagem = f"⚠️ Lacunas encontradas entre os intervalos de CEP para {tipo_objeto}:\n" + "\n".join(
    #                 gaps_formatados)
    #         else:
    #             mensagem = f"✅ Todos os intervalos de CEP para {tipo_objeto} estão conectados, sem lacunas."
    #
    #         mostrar_popup(mensagem)
    #         print(mensagem)
    #
    #     try:
    #         verificar_lacunas_por_tipo("Envelope")
    #         verificar_lacunas_por_tipo("Pacote")
    #     except Exception as ex:
    #         status.value = f"Erro ao exportar colunas específicas para Excel: {ex}"
    #         page.update()

    #A1 = ft.Checkbox(label="A1", value=False)
    #B1 = ft.Checkbox(label="B1", value=False)
    #C1 = ft.Checkbox(label="C1", value=False)
    #D1 = ft.Checkbox(label="D1", value=False)

    filtro_botao.on_click = aplicar_filtro
    filtro_campo.on_submit = aplicar_filtro
    registros_por_pagina_dropdown.on_change = on_registros_por_pagina_change
    dropdown.on_change = carregar_dados
    export_button.on_click = exportar_para_excel
    export_colunas_button.on_click = exportar_colunas_especificas
    conferiri_cep_button.on_click = verificador_ceps
    carregar_tabelas()
    b = ft.ElevatedButton(text="Gerar Plano", on_click=button_clicked)


    def on_nav_change(e):
        page.clean()
        page.add(nav_bar)
        match e.control.selected_index:
            case 0:
                page.add(ft.Text("🏠 Página Inicial"))
            case 1:
                page.add(
                    ft.AppBar(title=ft.Text("Editor de Tabelas Mysql", color=ft.colors.WHITE),
                              bgcolor=ft.colors.BLUE_700),
                    ft.Column([
                        ft.Column([
                            # ft.Text("Editor de Tabelas MySQL", size=26, weight=ft.FontWeight.BOLD),
                            ft.Row([
                                dropdown,
                                registros_por_pagina_dropdown,
                                filtro_campo,
                                filtro_rampa,
                                filtro_tipo_objeto,
                                filtro_botao,
                            ]),
                            ft.Column(controls=[ft.Row([data_table], scroll=ft.ScrollMode.ADAPTIVE)],
                                      scroll=ft.ScrollMode.ADAPTIVE),
                            ft.Row([paginacao]),

                        ]),
            # ft.Container(
            #     bgcolor="#ddeaf3",
            #     padding=15,
            #     border_radius=10,
            #     content=ft.Column([
            #         #ft.Text("Editor de Tabelas MySQL", size=26, weight=ft.FontWeight.BOLD),
            #         ft.Row([
            #             dropdown,
            #             registros_por_pagina_dropdown,
            #             filtro_campo,
            #             filtro_rampa,
            #             filtro_tipo_objeto,
            #             filtro_botao,
            #         ]),
            #         ft.Column(controls=[ft.Row([data_table], scroll=ft.ScrollMode.ADAPTIVE)],
            #                   scroll=ft.ScrollMode.ADAPTIVE),
            #         ft.Row([paginacao]),
            #
            #     ])
            # ),
            #ft.Divider(thickness=2, color="#999999"),

            ft.Row([
                export_button,
                export_colunas_button,
                salvar_button
            ], spacing=20, alignment=ft.MainAxisAlignment.CENTER),

            status
        ]),
                         )
            case 2:
                page.add(ft.AppBar(title=ft.Text("Verificar Cep de Triagem", color=ft.colors.WHITE),
                              bgcolor=ft.colors.BLUE_700),
                    ft.Column([
                        ft.Column([
                            # ft.Text("Verificador de  Tabelas", size=26, weight=ft.FontWeight.BOLD),
                            ft.Row([
                                dropdown,
                                # registros_por_pagina_dropdown,
                                # filtro_campo,
                                # filtro_rampa,
                                # filtro_tipo_objeto,
                                # filtro_botao,
                            ]),
                            # ft.Column(controls=[ft.Row([data_table], scroll=ft.ScrollMode.ADAPTIVE)],
                            #           scroll=ft.ScrollMode.ADAPTIVE),
                            # ft.Row([paginacao]),
                        ]),
                        # ft.Container(
                        #     bgcolor="#ddeaf3",
                        #     padding=15,
                        #     border_radius=10,
                        #     content=ft.Column([
                        #         #ft.Text("Verificador de  Tabelas", size=26, weight=ft.FontWeight.BOLD),
                        #         ft.Row([
                        #             dropdown,
                        #             #registros_por_pagina_dropdown,
                        #             #filtro_campo,
                        #             #filtro_rampa,
                        #             #filtro_tipo_objeto,
                        #            #filtro_botao,
                        #         ]),
                        #         # ft.Column(controls=[ft.Row([data_table], scroll=ft.ScrollMode.ADAPTIVE)],
                        #         #           scroll=ft.ScrollMode.ADAPTIVE),
                        #         # ft.Row([paginacao]),
                        #     ])
                        # ),

                        ft.Row([
                            ft.FilledButton("VERIFICAR CEP", on_click=verificador_ceps)

                        ], spacing=20, alignment=ft.MainAxisAlignment.CENTER),
                        status
                    ]),
                )
            case 3:
                page.add(ft.AppBar(title=ft.Text("Deletar Tabela", color=ft.colors.WHITE),
                              bgcolor=ft.colors.BLUE_700),
                    ft.Column([
                        ft.Column([
                            ft.Text("Deletar Tabela", size=20, weight="bold"),
                            dropdown_tabelas,
                            ft.FilledButton("DELETAR", on_click=ao_deletar_tabela)
                        ]),

                        # ft.Container(
                        #     padding=10,
                        #     bgcolor="#fff4f4",
                        #     border=ft.border.all(1, ft.colors.RED_200),
                        #     border_radius=8,
                        #     content=ft.Column([
                        #         ft.Text("Deletar Tabela", size=20, weight="bold"),
                        #         dropdown_tabelas,
                        #         ft.FilledButton("DELETAR", on_click=ao_deletar_tabela)
                        #     ])
                        # ),

                        ft.Divider(),
                        #status
                    ]),
                )
            case 4:
                page.add(ft.AppBar(title=ft.Text("Comparador de Planos de Triagem", color=ft.colors.WHITE),
                              bgcolor=ft.colors.BLUE_700),ft.Column([
                    #ft.Text("Duplicar uma tabela do MySQL", size=24, weight=ft.FontWeight.BOLD),
                    dropdown_tabelas,
                    input_novo_nome,
                    ft.ElevatedButton("Duplicar Tabela", on_click=ao_duplicar),
                    resultado
                ]), )
            case 5:
                page.add(ft.AppBar(title=ft.Text("Gerador de Planos/Regras", color=ft.colors.WHITE),
                              bgcolor=ft.colors.BLUE_700),dropdown_tabelas,
                         ft.FilledButton("DELETAR", on_click=ao_deletar_tabela(None)),
                         ft.Container(
                             padding=10,
                             bgcolor="#fff4f4",
                             border=ft.border.all(1, ft.colors.RED_200),
                             border_radius=8,
                             content=ft.Column([
                                 ft.Text("Deletar Tabela", size=20, weight="bold"),
                                 dropdown_tabelas,
                                 ft.FilledButton("DELETAR", on_click=ao_deletar_tabela)
                             ])
                         ), )
            case 6:
              page.add(
                  ft.AppBar(title=ft.Text("Testador de Plano MIS", color=ft.colors.WHITE),
                              bgcolor=ft.colors.BLUE_700),
                  ft.Column([
                      ft.Text("Selecione os arquivos para comparar:", size=16, weight=ft.FontWeight.BOLD),
                      ft.Row([
                          ft.Column([
                              autocomplete_input,
                              autocomplete_container,
                          ], width=400),
                          ft.Text(ref=xml_file_path, value="Nenhum arquivo XML selecionado", expand=True),
                      ]),
                      ft.Row([
                          ft.ElevatedButton("Selecionar Arquivo Excel (.xlsx/.xls)", icon=ft.icons.UPLOAD_FILE,
                                              on_click=lambda _: excel_file_picker.pick_files(
                                                  allow_multiple=False,
                                                  file_type=ft.FilePickerFileType.CUSTOM,
                                                  allowed_extensions=["xlsx", "xls"]
                                              )),
                          ft.Text(ref=excel_file_path, value="Nenhum arquivo Excel selecionado", expand=True),
                      ]),
                      ft.Divider(),
                      ft.Row([
                          ft.ElevatedButton("Comparar Arquivos", icon=ft.icons.COMPARE_ARROWS,
                                              on_click=process_comparison,
                                              bgcolor=ft.colors.GREEN_600, color=ft.colors.WHITE,
                                              width=200, height=40),
                          ft.ElevatedButton("Exportar Resultado", icon=ft.icons.DOWNLOAD,
                                              on_click=export_result_to_txt,
                                              bgcolor=ft.colors.BLUE_600, color=ft.colors.WHITE,
                                              width=200, height=40),
                      ]),
                      ft.Divider(),
                      ft.Column(ref=results_content, scroll=ft.ScrollMode.ADAPTIVE, expand=True, spacing=5)
                  ], expand=True, spacing=15, alignment=ft.MainAxisAlignment.START,
                      horizontal_alignment=ft.CrossAxisAlignment.START)
              )


    nav_bar = ft.NavigationBar(
        destinations=[

            ft.NavigationDestination(icon=ft.icons.HOME, label="Início"),
            ft.NavigationDestination(icon=ft.icons.UPDATE, label="Update Tabela "),
            ft.NavigationDestination(icon=ft.icons.CHECK, label="Verificador Cep!"),
            ft.NavigationDestination(icon=ft.icons.DELETE, label="Delete"),
            ft.NavigationDestination(icon=ft.icons.ADD_BUSINESS, label="Duplicar Tabela"),
            ft.NavigationDestination(icon=ft.icons.ACCOUNT_BALANCE_SHARP, label="Regras/Gerador de Plano"),
            ft.NavigationDestination(icon=ft.icons.START, label="Testador de Plano MIS"),

        ],
        on_change=on_nav_change,
    )
    page.add(nav_bar)
    ao_carregar(None)
"""
    #page.add(a1, b2, c3, d4, c5, b, t)
    page.add(nav_bar,
             

        ft.Column([
            ft.Container(
                bgcolor="#ddeaf3",
                padding=15,
                border_radius=10,
                content=ft.Column([
                    ft.Text("Editor de Tabelas MySQL", size=26, weight=ft.FontWeight.BOLD),
                    ft.Row([
                        dropdown,
                        registros_por_pagina_dropdown,
                        filtro_campo,
                        filtro_rampa,
                        filtro_tipo_objeto,
                        filtro_botao,
                    ]),
                    ft.Column(controls=[ft.Row([data_table], scroll=ft.ScrollMode.ADAPTIVE)],
                              scroll=ft.ScrollMode.ADAPTIVE),
                    ft.Row([paginacao]),

                ])
            ),

            ft.Divider(thickness=2, color="#999999"),

            ft.Container(
                content=data_table,
                padding=10,
                bgcolor="#ffffff",
                border=ft.border.all(1, ft.colors.GREY_300),
                border_radius=8,
                margin=10
            ),

            paginacao,

            ft.Divider(thickness=2, color="#999999"),

            ft.Row([
                export_button,
                export_colunas_button,
                salvar_button
            ], spacing=20, alignment=ft.MainAxisAlignment.CENTER),

            ft.Divider(),

            ft.Container(
                padding=10,
                bgcolor="#f3f8ff",
                border=ft.border.all(1, ft.colors.GREY_300),
                border_radius=8,
                content=ft.Column([
                    ft.Text("Duplicar Tabela", size=20, weight="bold"),
                    dropdown_tabelas,
                    input_novo_nome,
                    ft.ElevatedButton("Duplicar Tabela", on_click=ao_duplicar),
                    resultado
                ])
            ),

            ft.Container(
                padding=10,
                bgcolor="#fff4f4",
                border=ft.border.all(1, ft.colors.RED_200),
                border_radius=8,
                content=ft.Column([
                    ft.Text("Deletar Tabela", size=20, weight="bold"),
                    dropdown_tabelas,
                    ft.FilledButton("DELETAR", on_click=ao_deletar_tabela)
                ])
            ),

            ft.Divider(),
            status
        ]),


        ###########################################################################################################
        ft.Column([
        #ft.Row([dropdown, registros_por_pagina_dropdown, filtro_campo, filtro_botao]),
        ft.Row([
            dropdown,
            registros_por_pagina_dropdown,
            filtro_campo,
            filtro_rampa,
            filtro_tipo_objeto,
            filtro_botao,
        ]),

        ft.Column(controls=[ft.Row([data_table], scroll=ft.ScrollMode.ADAPTIVE)], scroll=ft.ScrollMode.ADAPTIVE),
        ft.Row([paginacao]),
        #ft.Row([paginacao,ft.Container(button_clicked())]),
        # Adiciona o botão de salvar aqui
        #ft.Row([export_button, export_colunas_button, salvar_button,a1, b2, c3, d4, c5,c6, b, t], spacing=20),
        ft.Row([export_button, export_colunas_button, salvar_button, ], spacing=20),
        ft.Row([ c5,c6, b, t], spacing=20),
        #ft.Row([A1,B1,C1,D1,E1,I1,J1,K1,K2,L1,L2,M1,N1,O1,P1,S1,T1],spacing=20,alignment=ft.MainAxisAlignment.END),
        #ft.Row([Envelope,Pacote],spacing=20,alignment=ft.MainAxisAlignment.END),
        #ft.Row(controls=[ft.ElevatedButton("Abrir Página de Desenvolvimento", on_click=open_dev_page),ft.Column(controls=[SRO,SEDEX,PAC],alignment=ft.MainAxisAlignment.END),ft.Column(controls=[ft.Column(controls=[Envelope,Pacote,PAC], alignment=ft.MainAxisAlignment.END),])],),
        ft.Row(controls=[ft.ElevatedButton("Abrir Página de Desenvolvimento",bgcolor=ft.colors.BLUE_700, on_click=open_dev_page),],),
        ft.Divider(color=ft.colors.RED),
        ft.Column([
            ft.Text("Duplicar uma tabela do MySQL", size=24, weight=ft.FontWeight.BOLD),
            dropdown_tabelas,
            input_novo_nome,
            ft.ElevatedButton("Duplicar Tabela", on_click=ao_duplicar),
            resultado
        ]),
        ft.Divider(color=ft.colors.GREEN),
        #ft.Column([ft.Text("Deletar tabela do MySQL"),ft.Row(controls=[dropdown_tabelas,ft.FilledButton("Apagar", on_click=dropdown_tabelas ]))),
        dropdown_tabelas,
        ft.FilledButton("DELETAR",on_click=ao_deletar_tabela(None)),
        ft.Container(
            padding=10,
            bgcolor="#fff4f4",
            border=ft.border.all(1, ft.colors.RED_200),
            border_radius=8,
            content=ft.Column([
                ft.Text("Deletar Tabela", size=20, weight="bold"),
                dropdown_tabelas,
                ft.FilledButton("DELETAR", on_click=ao_deletar_tabela)
            ])
        ),

        ft.Divider(),






        status
    ]))
    """
    # Carrega tabelas ao iniciar
    # ao_carregar(None)


ft.app(target=main)