import pandas as pd  # for data manipulation
#from imblearn.over_sampling import SMOTE
import numpy as np  # for numerical computing
import matplotlib.pyplot as plt  # for plotting
#import seaborn as sns  # for advanced plotting
from sklearn.model_selection import train_test_split  # for splitting data into training and testing sets
import statsmodels.api as sm  # for fitting regression models
import sklearn.metrics as metrics  # for evaluating model performance
import Riot_API_SQLv2  # Scripts defined in Riot_API_SQLv2

query = F"SELECT * FROM [Data_Science_RIOT].[dbo].[vw_GameSummary]"
Riot_API_SQLv2.Config.cursor.execute(query)
game_log = Riot_API_SQLv2.Config.cursor.fetchall()
table = Riot_API_SQLv2.table_data('vw_GameSummary', 'Data_Science_RIOT.')
data = pd.DataFrame(data=game_log, columns=table.keys())
x = data.iloc[:, 1:]
y = data["win"]
x_train, x_test, y_train, y_test = train_test_split(x,  # the predictors or independent variables
                                                    y,  # the outcome or dependent variable
                                                    train_size=0.8,  # 80% training data
                                                    test_size=0.2,  # 20% test data
                                                    random_state=1812)
#print(x_train)
#print(y_train)
model = sm.Logit(y_train, sm.add_constant(x_train), missing='raise').fit()
print(model.summary())
predicted = model.predict(sm.add_constant(x_test))
predicted_class = np.where(predicted >= 0.5, 1, 0)
print(metrics.classification_report(y_true=y_test, y_pred=predicted_class))

# Compute the confusion matrix
cm = metrics.confusion_matrix(y_true=y_test, y_pred=predicted_class)
cm_display = metrics.ConfusionMatrixDisplay(confusion_matrix=cm)
cm_display.plot(values_format='')
# Set the figure size for the confusion matrix display
plt.rcParams["figure.figsize"] = (5, 6)

# Create a ConfusionMatrixDisplay object with the computed confusion matrix and display labels
fpr, tpr, _ = metrics.roc_curve(y_true=y_test, y_score=predicted)

# Create a new plot for the ROC curve
plt.figure()

# Plot the ROC curve with a dark orange color and a linewidth of 2
plt.plot(fpr, tpr, color="darkorange", lw=2, label=f"ROC curve (AUC = {metrics.auc(fpr, tpr):.2f})")

# Plot the diagonal line representing a random classifier with a navy color, linewidth of 2, and dashed linestyle
plt.plot([0, 1], [0, 1], color="navy", lw=2, linestyle="--")

# Set the axis labels and title
plt.xlabel("False Positive Rate")
plt.ylabel("True Positive Rate")
plt.title("Receiver Operating Characteristic (ROC) Curve")

# Add a legend to the plot
plt.legend(loc="lower right");

plt.show()
