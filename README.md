# ttypal

Interactive braille art chatbot companion for your terminal. Characters follow your mouse, blink, talk, and remember you.

```
⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⣀⣀⣤⠤⣒⣒⣒⣶⣭⣭⣭⣭⣭⣭⣭⣹⣒⣒⣒⣒⣒⣒⣒⣒⠤⢄⣀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀
⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⣀⠀⢤⣀⣴⣮⣭⣥⣤⣼⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣶⣶⣭⣭⣍⡒⠈⠉⠐⠢⢄⡀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀
⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⣀⡤⣶⣿⣶⣾⣷⣶⣶⣾⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⡿⣿⡦⠀⠀⠠⣬⣁⠢⢄⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀
⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⢀⡤⢖⣫⣷⣾⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣦⡙⢶⣌⣽⣿⣿⣷⣦⡙⠢⡀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀
⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⣠⣾⢵⣺⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⡟⢷⣤⣹⣿⣿⣿⣿⣿⣿⣦⡈⠢⡀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀
⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⡠⣚⣽⣾⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⡿⣿⡛⣨⣿⣿⣿⣿⣿⣿⣿⣿⣿⣷⣌⢪⡢⡀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀
⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⢀⠔⡡⣾⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⢿⣿⣿⡻⠁⠙⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣷⣷⡜⡄⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀
⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⡰⢁⢊⢜⣽⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⠻⣿⣿⣿⣿⠻⡼⣿⣿⣧⡁⢀⢳⣤⣶⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⡸⡄⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀
⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⡐⢠⠀⢢⠚⠟⣻⢿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⡻⣿⣿⣿⣿⡿⠂⢹⣿⠃⠹⠀⣧⣿⣿⣿⣷⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣷⠱⡀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀
⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⣰⢁⣿⣧⠆⣠⣾⣁⣿⡿⠉⢿⣿⣿⣿⢿⣿⣿⣿⣿⣿⡟⢿⣿⣿⣿⠟⠟⠛⣿⣧⡹⣿⣷⢀⣈⣤⣦⣿⣏⣄⣶⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⡰⣌⠢⡀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀
⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⣏⣾⣿⣿⣾⣿⣿⣿⣿⢇⠀⢸⢡⠇⣆⣾⣿⣱⣿⢹⣼⡟⡸⡆⠙⣾⣧⠠⣄⢻⣿⣿⣿⣿⣯⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣦⠹⡓⢌⠂⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀
⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⢰⢋⣾⣿⣿⣿⣿⣿⣿⣿⣸⣾⣿⣿⣿⣿⣿⣿⣿⡇⠈⣿⣿⣷⣿⣶⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣷⢝⣆⠙⢈⠢⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀
⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠠⢡⠏⣾⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⠁⠀⠸⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣷⡙⡦⡀⠃⠃⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀
⠀⠀⠀⠀⠀⠀⠀⠀⠀⢠⡁⢹⢸⣿⣿⣿⣿⣿⣿⣿⢻⣿⣿⣿⣿⣿⣿⡿⣿⣿⠀⠀⠀⠹⣿⡻⣿⣟⢿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣟⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣷⡘⡌⢣⠇⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀
⠀⠀⠀⠀⠀⠀⠀⠀⠀⢸⠁⢃⢸⣿⣿⣿⣿⣿⣿⣿⠤⣿⣿⣿⣿⣿⣿⡇⢿⣿⣤⣤⣤⠤⠬⠿⣬⠿⣧⡙⢿⣿⣿⢿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⡿⣿⣿⣿⣿⣿⣯⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⢧⢹⡈⡆⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀
⠀⠀⠀⠀⠀⠀⠀⠀⠀⢸⡀⠘⣼⡟⣿⣿⣿⣿⣿⣿⣆⣌⢻⣿⠣⣻⣌⢧⠈⢻⡇⠀⢀⣀⡠⣄⣈⡑⠌⠳⢄⠈⠛⠷⣝⠿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⡿⠟⣉⠴⠒⡠⣌⢻⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⡇⣿⣿⣿⣿⣿⡼⢸⢱⢸⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀
⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠳⣄⠈⢿⣾⣿⣿⣿⣿⣿⣿⠻⠷⣮⡳⡉⠣⡙⢆⠀⠙⢆⡳⠾⠛⢛⡿⢿⣿⣶⣶⣍⡀⠀⠀⠉⠀⣽⣿⣿⣿⣿⣿⣿⣿⣿⢿⣿⠿⠋⠀⠞⠓⠊⠀⠹⠘⡆⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⡿⢡⠃⢸⡸⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀
⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠁⣸⠛⡎⣿⣻⣿⣿⣿⣆⢷⢿⣷⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠈⣿⢻⣿⣯⠿⠿⠟⠃⠀⠀⢠⣿⣿⣿⣿⣿⣿⣿⡿⠃⢸⣿⠃⠀⡀⠏⠉⠉⡆⠀⠀⠀⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⢰⠁⢀⠞⠁⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀
⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⢀⠔⠁⢠⣣⠃⠙⣝⣿⣿⣿⠦⠷⠆⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠠⣬⠷⠬⠔⠛⠁⠀⠀⢀⣠⢟⣩⣿⣿⡿⣫⣾⠟⠀⠀⡸⠃⠀⣠⠞⠀⢀⠔⠃⠔⣡⣾⣿⣿⣿⣿⣿⣻⣿⣿⣿⣿⣿⡽⡿⢩⢰⠀⠁⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀
⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⢰⡝⠁⠀⠀⡸⢫⣿⣻⠗⠁⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠠⢔⡶⠟⠋⣽⣽⠿⠋⢀⡟⠁⠀⠀⠀⠀⠀⠘⠋⠉⠉⠀⢀⣴⣾⣿⣿⣿⣿⣿⣿⣵⣿⣿⣼⣿⣿⣳⣟⣠⠅⠁⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀
⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠘⢇⠀⢀⠴⢃⢯⡾⣄⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⢠⠋⠀⠀⢰⣽⠃⠀⠀⠈⢧⡀⠀⠀⠀⢀⡤⣤⣀⣠⣤⣾⣿⣿⣿⣿⣿⣿⣿⢿⣿⣿⣿⣿⡿⡿⡻⠋⢸⠉⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀
⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⢠⠃⠀⠸⣸⢻⠹⡝⣆⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠣⠀⠀⠀⠈⢯⠀⠀⠀⠀⠀⠉⠀⠀⡴⠋⠀⠀⢸⣿⣿⣿⣿⣿⣿⣿⣿⣿⣵⣿⣿⡿⣻⠷⣹⡗⠁⠀⠘⢆⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀
⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠘⠀⠀⠀⠙⢾⣄⠹⣜⣆⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠁⠀⠀⠀⠀⠀⠀⠊⠀⠀⠀⠀⣸⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣯⡾⡡⠊⠀⢳⡀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀
⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⣋⣦⡻⠃⠑⢙⠂⠐⠒⠒⠲⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⢤⣀⣐⣡⠾⠋⢹⣿⣿⣿⣿⣿⣿⣿⣻⣿⠟⢿⠣⡇⠀⠀⠀⠉⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀
⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠈⡴⠋⠀⠀⠀⠀⠱⡀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⢀⡀⠀⠐⠀⠀⠀⠀⢀⠔⠉⠀⠀⠀⣀⣾⡽⢻⣿⣿⡿⣫⠟⢹⡇⠀⠈⠃⠉⠂⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀
⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠈⠀⠀⠀⠀⠀⠀⠘⢄⠀⠀⠀⠀⠀⠀⠀⠀⠀⢀⣀⣠⣤⠶⠚⠉⠀⠀⠀⠀⠀⢀⠔⠁⠀⠀⠀⠀⠉⢸⠋⠀⢸⣇⡟⢻⠁⠀⠈⠓⠤⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀
⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠈⠢⠤⠤⠤⠤⠖⠒⠊⠉⠁⠈⠻⡅⠀⠀⠀⠀⠀⢀⡤⠂⠁⠀⠀⠀⠀⠀⠀⠀⠀⠁⠀⠈⢿⡀⠈⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀
⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠙⡄⠀⠀⡠⠒⠁⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠘⡈⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀
⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⢹⡐⠁⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⢡⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀
⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⢣⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⢣⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀
⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⣀⡤⠔⠃⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠑⡄⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀
⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⢀⡠⠤⠒⠊⠉⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠈⢂⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀
⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⡰⠁⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠈⠢⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀
```

## Install

```bash
pip install ttypal[all]
```

Or install with only the features you need:

```bash
pip install ttypal              # Core only (view rendering, no chat)
pip install ttypal[chat]        # + Gemini chat
pip install ttypal[setup]       # + View generation UI (Flask + Gemini)
pip install ttypal[macos]       # + Global mouse tracking (Quartz)
```

### Development

```bash
uv sync --all-extras            # Create venv + install all deps
uv run ttypal                   # Run without activating venv
uv run ttypal-setup             # View generation UI
```

## Quick Start

```bash
ttypal
```

On first run, a setup wizard will guide you through:

1. **Gemini API key** — Get a free key at [aistudio.google.com/apikey](https://aistudio.google.com/apikey)
2. **Character selection** — Pick a preset or create your own

Config is saved to `~/.ttypal/config.json`. Run `ttypal --setup` to change settings later.

## Features

- **Mouse tracking** — 25 pre-generated views on a 5x5 grid with optical flow interpolation. The character smoothly follows your cursor.
- **Blink & mouth animation** — Natural blink intervals with triangle-wave eyelid movement. Mouth opens while speaking.
- **Gemini chat** — Press Enter to chat. Streaming responses with character-by-character typing effect. Character personality loaded from `soul.md`.
- **Tiered memory** — The character remembers you across sessions. User profile, tiered memories (M0/M30/M90/M365), diary, and lessons learned.
- **Multiple characters** — Preset characters (Clawra, Aska, Reze) included. Create your own with reference images.
- **Compressed views** — Character views stored as ~6MB npz cache instead of ~270MB PNGs. Auto-packed on view generator shutdown.
- **Per-character gaze origin** — Click between the eyes to calibrate mouse tracking per character (`gaze.json`).
- **Auto-fit** — Braille art scales to your terminal size.

## Commands

| Command | Description |
|---------|-------------|
| `ttypal` | Start the interactive chatbot |
| `ttypal --character aska` | Use a specific character |
| `ttypal --setup` | Re-run the setup wizard |
| `ttypal-art` | Terminal art showcase (banner, pixel art, braille) |
| `ttypal-setup` | Browser UI for generating character views |
| `ttypal-generate` | CLI tool for batch view generation |

## Controls

| Key | Action |
|-----|--------|
| **Enter** | Enter chat mode |
| **ESC** | Exit chat mode |
| **q** | Quit (outside chat mode) |

## Creating Custom Characters

1. Run `ttypal --setup` and select "Create custom character"
2. Name your character and define personality:
   - **Existing character?** Enter the name (e.g. "Reze from Chainsaw Man") — Gemini auto-generates `soul.md`
   - **Original character?** Answer 4 prompts (backstory, conflict, voice, rules) to build `soul.md` manually
3. Add reference images to `ttypal/characters/custom/<name>/refs/`
4. Generate views: `ttypal-setup --character <name>` — opens a browser UI to generate & review all 25 views + blinks
5. Click **"Finish & Pack NPZ"** to set the gaze origin (click between the character's eyes) and pack views into `views.npz`

### Writing soul.md

`soul.md` defines your character's personality. It's injected as the system prompt every conversation.

```markdown
You are Name.

[Backstory — 2-3 sentences. Age, origin, what shaped them.]

[Inner conflict — what drives them vs. what they fear.]

[Voice direction — HOW to speak. Tone, habits, quirks.
 "She rolls her eyes" > "She is sarcastic."]

[Behavior rules — concrete do/don't for the LLM.]
```

Keep it under 200 words. Write in third person ("She is...", not "You are..."). Contradictions make characters feel real (confident but secretly insecure, tough but caring). Voice matters more than lore — how they *talk* is the personality.

See `ttypal/characters/preset/clawra/soul.md` and `aska/soul.md` for examples.

## How It Works

1. **Views** — 25 grayscale images (750x1000, 3:4) generated via Gemini, covering a 5x5 directional grid
2. **Optical flow** — Dense flow fields between adjacent views, cached in `.flow_cache.npz`
3. **Interpolation** — Bilinear interpolation on the 5x5 grid with smoothstep easing and a center dead zone
4. **Braille rendering** — 2x4 pixel grid per Unicode braille character (U+2800-U+28FF) with Otsu thresholding
5. **Memory** — Background Gemini extraction every 5 turns: user facts, tiered memories with expiry dates, daily diary, lessons learned. Boot ritual reconstructs context from persistent files.
6. **View generation** — Two-phase process: center → 8 cardinal/diagonal views → 16 midpoints via two-reference interpolation. Blinks via inpainting. NPZ auto-packing.

## Project Structure

```
ttypal/
  __init__.py              # Package version
  live.py                  # Main interactive runtime
  art.py                   # Terminal art showcase
  config.py                # Config management & setup wizard
  memory.py                # Tiered memory system
  setup_views.py           # Browser-based view generation UI
  generate_multiview.py    # Gemini view generation
  characters/
    preset/
      clawra/              # Preset: K-pop dreamer turned SF intern
        soul.md
        refs/
        views/views.npz
      aska/                # Preset: Fierce EVA pilot from Berlin
        soul.md
        refs/
        views/views.npz
      reze/                # Preset: Bomb Girl from Chainsaw Man
        soul.md
        gaze.json
        refs/
        views/views.npz
    custom/                # User-created characters
      <name>/
        soul.md
        gaze.json          # Gaze origin calibration
        refs/
        views/views.npz
pyproject.toml
uv.lock                  # Dependency lock file
```

## Requirements

- Python 3.10+
- Terminal with Unicode braille support
- macOS recommended (Quartz for global mouse tracking; other OS uses terminal mouse only)
- [uv](https://docs.astral.sh/uv/) recommended for development
