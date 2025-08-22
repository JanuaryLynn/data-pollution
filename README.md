# Dynamic Evaluation of Governance Strategies for Mitigating Social Media Data Pollution: An Agent-Based Modeling Approach

This project aims to simulate the spread of data pollution on social media platforms, particularly caused by AI-generated content (such as synthetic text). It evaluates the effectiveness of different governance strategies, including legal interventions and platform self-regulation. The experiment uses Agent-Based Modeling (ABM) and is implemented through the NetLogo platform, enabling simulation, data export, and subsequent visualization.

## 📁 Project Structure

- `netlogo experiment/`  
  Contains NetLogo experiment models (`.nlogo`) and simulation configuration files.

- `experiment data/`  
  Stores all experiment data, including raw data exported from NetLogo's built-in BehaviorSpace tool and processed Excel files. Data is organized by experimental group.

- `visual analysis/`  
  Diagrams and figures generated from the visualization scripts, useful for academic presentation or publication.  And python scripts used for data visualization, mainly using `matplotlib` and `pandas`.

- `README.md`  
  This documentation file.

- `License.md`  
  Copyright statement.  
  
## 💻 How to Run the Simulation

1. Install NetLogo (version 6.4.0 or above recommended);
2. Navigate to the `netlogo experiment` folder and open the `.nlogo` file;
3. Use NetLogo's built-in **BehaviorSpace tool** to run batch simulations;
4. Exported data will be saved as `.csv` files in the `experiment data` folder;
5. Run Python scripts in the `visual analysis` folder to analyze and visualize results.

## 📦 Python Dependencies

To run the visualization scripts, please ensure the following Python libraries are installed:

```bash
pip install matplotlib pandas openpyxl
```

## 📌 Use Cases

This project is suitable for:

- Teaching and research on Agent-Based Modeling in computational social science;
- Investigating the diffusion of AIGC (AI-Generated Content) and misinformation governance on social media;
- Evaluating the comparative effectiveness of legal and technological governance mechanisms against data pollution.

## 📚 Citation

If you find this project useful for your academic research, please consider citing the related paper or acknowledging the author(s). Citation details will be added after formal publication.

## 🌻 Acknowledgments

Special thanks to my advisor, colleagues, and friends for their guidance and support throughout the design, implementation, and analysis of this project.  
Thanks for your reading.

## 📄 License

This project is licensed under the MIT License. You are free to copy, modify, and distribute the content with proper attribution and inclusion of the license notice.


