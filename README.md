# 📘 Projeto: Treinamento e Análise de Classificação com YOLOv8

Este repositório contém o notebook **`Mauricio_Jose_Ferlin_Tonnera_rm565469_fase6.ipynb`**, desenvolvido com o objetivo de demonstrar e documentar o processo de **treinamento, validação e teste** de um modelo de **classificação de imagens** utilizando a arquitetura **YOLOv8 (You Only Look Once)**.

---

## 🎯 Objetivo do Projeto

O trabalho visa apresentar um estudo prático sobre o uso de **redes neurais convolucionais (CNNs)** e da metodologia **YOLOv8** na tarefa de **classificação de objetos**.  
O conteúdo foi estruturado em formato acadêmico, incluindo:
- Preparação e organização do dataset (treino, validação e teste);
- Configuração do ambiente Google Colab e integração com Google Drive;
- Rotulagem das imagens via **MakeSense.AI**;
- Treinamento do modelo YOLOv8 com diferentes quantidades de épocas (30 e 60);
- Avaliação comparativa dos resultados obtidos;
- Discussão dos erros e métricas de desempenho (acurácia, perda, etc.).

---

## ⚙️ Ferramentas e Tecnologias Utilizadas

- **Linguagem:** Python 3  
- **Bibliotecas principais:**
  - [Ultralytics YOLOv8](https://github.com/ultralytics/ultralytics)
  - NumPy, Pandas, Matplotlib
  - Torch / PyTorch
- **Ambiente de execução:** Google Colab  
- **Armazenamento de dados:** Google Drive  
- **Rotulagem de imagens:** [MakeSense.AI](https://www.makesense.ai/)

---

## 🧩 Estrutura do Notebook

| Seção | Descrição |
|-------|------------|
| **1. Introdução e Fundamentação Teórica** | Contextualiza o modelo YOLO, o conceito de classificação e o uso de CNNs. |
| **2. Sumário e Análise** | Apresenta perguntas e respostas sobre o uso do YOLO, resultados de desempenho e próximos passos. |
| **3. Treinamento e Validação** | Demonstra o processo de treino do modelo, ajustes de épocas e análise de métricas. |
| **4. Avaliação e Discussão de Erros** | Interpreta os resultados e descreve erros como *KeyError* e *ValueError*, traduzidos e explicados tecnicamente. |

---

## 📊 Resultados Principais

- O modelo YOLOv8 obteve **acurácia Top-1 = 100%** no conjunto de teste reduzido.  
- Foram observadas diferenças mínimas de desempenho entre 30 e 60 épocas, evidenciando estabilidade do treinamento.  
- A análise técnica das exceções (*KeyError* e *ValueError*) foi documentada em português técnico, explicando causas e soluções.

---

## 🚀 Como Executar

1. Acesse o Google Colab: [https://colab.research.google.com](https://colab.research.google.com)  
2. Faça upload do notebook `.ipynb`.  
3. Conecte seu **Google Drive** e ajuste os caminhos do dataset.  
4. Execute as células sequencialmente (Shift + Enter).  
5. Acompanhe os resultados e gráficos gerados nas seções de treino e avaliação.

---

## 🧠 Referências

- **Ultralytics YOLOv8 Documentation:** https://docs.ultralytics.com  
- **MakeSense.AI:** https://www.makesense.ai/  
- **Goodfellow, I., Bengio, Y., & Courville, A.** (2016). *Deep Learning*. MIT Press.

---

## ✍️ Autor

**Mauricio Tonnera**  
Acadêmico e pesquisador em **Inteligência Artificial Aplicada**, com foco em **visão computacional, redes neurais e análise de dados**.  
📧 [Entre em contato via GitHub](https://github.com/)  

---

