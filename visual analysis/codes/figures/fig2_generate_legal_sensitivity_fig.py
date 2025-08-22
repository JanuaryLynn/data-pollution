import matplotlib.pyplot as plt
import numpy as np
import seaborn as sns

# Use professional theme, disable default title/font header
sns.set_theme(style="whitegrid")
plt.rcParams.update({
    'font.family': 'Times New Roman',  # IEEE recommended
    'font.size': 10,
    'axes.labelsize': 10,
    'axes.titlesize': 10,
    'xtick.labelsize': 9,
    'ytick.labelsize': 9
})

# Data
pollution_levels = [10, 30, 50]
titles = ['Low Pollution (10%)', 'Medium Pollution (30%)', 'High Pollution (50%)']
no_treatment = [14.943, 8.575, 5.240]
strength_values = [30, 60, 90]
strength_effect = [
    [18.273, 22.399, 28.453],
    [10.976, 13.875, 16.557],
    [7.314, 10.003, 12.524]
]
response_values = [1, 5, 10]
response_effect = [
    [99.459, 22.399, 19.477],
    [39.492, 13.875, 11.249],
    [32.820, 10.003, 7.594]
]

# Create figure with vertical layout, shared x/y axes
fig, axes = plt.subplots(3, 1, figsize=(5.5, 12), sharex=False, sharey=True)  # ~single column width

# Plot
for i, pollution in enumerate(pollution_levels):
    ax = axes[i]
    
    # Plot curves
    ax.plot(strength_values, strength_effect[i], 'o-',
            color='#1f77b4', linewidth=1.5, markersize=5,
            label='legal-strength (response-time=5)')
    ax.plot(response_values, response_effect[i], 's-',
            color='#ff7f0e', linewidth=1.5, markersize=5,
            label='legal-response-time (strength=60)')
    ax.axhline(y=no_treatment[i], linestyle='--', color='gray',
               label='no treatment')
    
    # Slope annotations for strength
    for j in range(len(strength_values) - 1):
        slope = (strength_effect[i][j + 1] - strength_effect[i][j]) / (strength_values[j + 1] - strength_values[j])
        norm_slope = slope * (strength_values[j] / strength_effect[i][j])
        ax.annotate(f'S={norm_slope:.2f}',
                    xy=((strength_values[j] + strength_values[j + 1]) / 2,
                        (strength_effect[i][j] + strength_effect[i][j + 1]) / 2),
                    xytext=(0, 12),
                    textcoords='offset points',
                    color='#1f77b4', backgroundcolor='white', fontsize=8)

    # Slope annotations for response
    for j in range(len(response_values) - 1):
        slope = (response_effect[i][j + 1] - response_effect[i][j]) / (response_values[j + 1] - response_values[j])
        norm_slope = slope * (response_values[j] / response_effect[i][j])
        ax.annotate(f'S={norm_slope:.2f}',
                    xy=((response_values[j] + response_values[j + 1]) / 2,
                        (response_effect[i][j] + response_effect[i][j + 1]) / 2),
                    xytext=(5, 8),
                    textcoords='offset points',
                    color='#ff7f0e', backgroundcolor='white', fontsize=8)

    # Axis labels
    ax.set_ylabel('Effectiveness')
    ax.set_xticks(strength_values)
    ax.set_xticklabels(strength_values)
    ax.set_xlabel('legal-strength')

    # Add second X-axis
    ax2 = ax.twiny()
    ax2.set_xlim(ax.get_xlim())
    ax2.set_xticks(response_values)
    ax2.set_xticklabels(response_values)
    ax2.set_xlabel('legal-response-time')

    # Add subfigure label centered below
    ax.text(0.5, -0.24, f'({chr(97+i)}) {titles[i]}',
            transform=ax.transAxes, ha='center', va='top', fontsize=9, fontweight='bold')

# Adjust spacing
plt.subplots_adjust(hspace=0.6)

# Add legend at top
handles, labels = axes[0].get_legend_handles_labels()
fig.legend(handles, labels,
           loc='upper center', bbox_to_anchor=(0.5, 0.99),
           ncol=1, frameon=False, fontsize=9,
           title='Legend (S = normalized sensitivity coefficient)', title_fontsize=9)

# Save to PDF
plt.savefig('parameter_sensitivity_vertical.pdf', format='pdf', dpi=600, bbox_inches='tight')
plt.show()
plt.close
Print ('fig2的pdf成功输出')