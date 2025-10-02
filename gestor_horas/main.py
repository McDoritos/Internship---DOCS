import json
import os
from datetime import datetime, timedelta

REGISTO_FILE = 'registo.json'
HORAS_SEMANAIS = 16

def carregar_registo():
    if not os.path.exists(REGISTO_FILE):
        return []
    with open(REGISTO_FILE, 'r', encoding='utf-8') as f:
        return json.load(f)

def guardar_registo(registo):
    with open(REGISTO_FILE, 'w', encoding='utf-8') as f:
        json.dump(registo, f, indent=4, ensure_ascii=False)

def nova_semana():
    hoje = datetime.today()
    segunda = hoje - timedelta(days=hoje.weekday())
    return {
        "inicio_semana": segunda.strftime('%Y-%m-%d'),
        "tarefas": []
    }

def atualizar_semana_se_necessario(registo):
    """Cria uma nova semana apenas se já mudou a semana atual (segunda-feira),
       comparando só as datas — assim não somos enganados pela hora do dia."""
    hoje = datetime.today()
    # comparar apenas as datas (sem hora)
    segunda_hoje_date = (hoje - timedelta(days=hoje.weekday())).date()

    if not registo:
        registo.append(nova_semana())
        return

    # converter a string guardada para date()
    ultima_semana_date = datetime.strptime(registo[-1]['inicio_semana'], '%Y-%m-%d').date()

    # só criar nova semana se a segunda-feira actual for posterior à última registada
    if segunda_hoje_date > ultima_semana_date:
        registo.append(nova_semana())

def obter_semana_atual(registo):
    """Devolve a semana atual (última entrada), sem criar nova."""
    if not registo:
        return None
    return registo[-1]

def adicionar_tarefa(registo, descricao, horas):
    semana = obter_semana_atual(registo)
    if semana is None:
        registo.append(nova_semana())
        semana = registo[-1]

    semana['tarefas'].append({
        "descricao": descricao,
        "horas": round(horas, 2),
        "data": datetime.today().strftime('%Y-%m-%d %H:%M')
    })

def horas_gastas_semana(semana):
    return sum(tarefa['horas'] for tarefa in semana['tarefas'])

def mostrar_resumo(semana):
    print(f"\n🗓 Semana iniciada em {semana['inicio_semana']}")
    total = horas_gastas_semana(semana)
    print(f"⏱ Total de horas gastas: {total:.2f}h")
    if total > HORAS_SEMANAIS:
        print(f"⚠️ Ultrapassaste o limite de {HORAS_SEMANAIS}h semanais!")
    else:
        restante = HORAS_SEMANAIS - total
        print(f"✅ Ainda tens {restante:.2f}h disponíveis esta semana.")
    print("\n📋 Tarefas:")
    if not semana['tarefas']:
        print("   (Sem tarefas ainda)")
    for t in semana['tarefas']:
        print(f" - [{t['data']}] {t['descricao']} ({t['horas']:.2f}h)")

def mostrar_historico(registo):
    if not registo:
        print("\n📭 Ainda não há registos.")
        return

    print("\n📚 Histórico de Tarefas por Semana:")
    for semana in registo:
        print(f"\n🔹 Semana iniciada em {semana['inicio_semana']}")
        total = horas_gastas_semana(semana)
        print(f"   Total: {total:.2f}h")
        if not semana['tarefas']:
            print("    (Sem tarefas)")
        for t in semana['tarefas']:
            print(f"    - [{t['data']}] {t['descricao']} ({t['horas']:.2f}h)")

def editar_tarefa(registo):
    semana = obter_semana_atual(registo)
    if not semana or not semana['tarefas']:
        print("📭 Não há tarefas para editar esta semana.")
        return

    print("\n📋 Tarefas desta semana:")
    for i, t in enumerate(semana['tarefas'], start=1):
        print(f"{i}. [{t['data']}] {t['descricao']} ({t['horas']:.2f}h)")

    try:
        escolha = int(input("\nQual tarefa queres editar? (número): "))
        if escolha < 1 or escolha > len(semana['tarefas']):
            print("❌ Número inválido.")
            return

        tarefa = semana['tarefas'][escolha - 1]
        print(f"Selecionaste: {tarefa['descricao']} ({tarefa['horas']:.2f}h)")
        novo_valor = float(input("Novo número de horas: ").replace(',', '.'))
        if novo_valor <= 0:
            print("❌ O valor tem de ser maior que 0.")
            return

        tarefa['horas'] = round(novo_valor, 2)
        guardar_registo(registo)
        print("✅ Tarefa atualizada com sucesso!")

    except ValueError:
        print("❌ Entrada inválida.")

def menu():
    registo = carregar_registo()
    atualizar_semana_se_necessario(registo)
    guardar_registo(registo)

    while True:
        print("\n====== Gestor de Horas Semanais ======")
        print("1. Adicionar tarefa")
        print("2. Ver resumo da semana atual")
        print("3. Ver histórico completo")
        print("4. Editar tarefa da semana atual")
        print("5. Sair")

        opcao = input("Escolhe uma opção: ")

        if opcao == '1':
            descricao = input("Descrição da tarefa: ")
            try:
                horas = float(input("Horas gastas (ex: 1.5 para 1h30): ").replace(',', '.'))
                if horas <= 0:
                    print("❌ Introduz um valor maior que 0.")
                    continue
                adicionar_tarefa(registo, descricao, horas)
                guardar_registo(registo)
                print("✅ Tarefa adicionada com sucesso.")
            except ValueError:
                print("❌ Erro: Introduz um número válido para as horas.")

        elif opcao == '2':
            semana = obter_semana_atual(registo)
            if semana:
                mostrar_resumo(semana)
            else:
                print("📭 Ainda não há semanas registadas.")

        elif opcao == '3':
            mostrar_historico(registo)

        elif opcao == '4':
            editar_tarefa(registo)

        elif opcao == '5':
            print("👋 Até à próxima!")
            break

        else:
            print("❌ Opção inválida.")

if __name__ == '__main__':
    menu()
