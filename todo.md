1 [DONE] usar o banco de dados para atualizar a lista de preços no BOM ao invez de puxar os dados pela api toda vez
2 [DONE] nova aba de reprocessamento: calcular se vale a pena reprocessar um item e vender os componentes ou vender o item em si. a aba aceita uma lista de itens e retorna duas listas (reprocessar / vender), cada lista formatada com a syntax de busca multipla do inventario in-game para facilitar a seleção dos itens. deve ter um menu dropdown para escolher o mercado fonte dos valores usados na comparação.
3 [DONE] fazer o calculo do BOM de todos os itens e componentes (recursivo: componentes dos componentes)
4 [DONE] usar flag para items BOM que não serão atomizados (nesses casos o item será comprado pronto)
5 [DONE] eficiencia de material deve ser por item no BOM para os itens manufaturados
6 [DONE] ver se tem como puxar quais rigs uma estrutura de manofatura tem instalado pela api — ESI não expõe rigs/fitting; cadastro manual implementado
7 [DONE] usando o ponto 6 implementar um sistema de cadastro de estrutura para usar em menu dropdown no BOM — implementado em Configurações > Estruturas de Manufatura
8 [DONE] adicionar os bonus das estaçoes na janela de configuraçoes ( ME, TE) e usar esses bonus no BOM
9 [DONE] fazer um lado a lado de itens comparando os preços do mercado escolhido com o mercado de jita ou amarr no BOM para saber oque vale apena comprar ou importar na hora da produção
10 [DONE] melhorar a fila de produção com um panhado de todos os itens que será usado para produzir tudo
11 [DONE] melhorar o ranking com uma projeção do mercado para o volume de venda da ultima semana( janela de tempo configuravel 1 semana , 2 semanas, 1 mês) fazer essa ideia como uma pagina que abre quando se clica no item da lista do ranking.
12 [DONE] futuro, fazer um sistema de graficos mostrando o volume atual e preditivo do mercado para a tela de ranking.
