# FCN model
# when tuning start with learning rate->mini_batch_size -> 
# momentum-> #hidden_units -> # learning_rate_decay -> #layers 
import tensorflow.keras as keras
import tensorflow as tf
import numpy as np
import os
import time
import ast
from copy import deepcopy

from utils.utils import save_logs
from utils.utils import calculate_metrics

class Classifier_FCN:

    def __init__(self, output_directory, input_shape, nb_classes, verbose=False, build=True):
        self.output_directory = output_directory
        if build == True:
            self.model = self.build_model(input_shape, nb_classes)
            if(verbose==True):
                self.model.summary()
            self.verbose = verbose
            self.model.save_weights(self.output_directory+'model_init.hdf5')
        return

    def build_model(self, input_shape, nb_classes):
        input_layer = keras.layers.Input(input_shape)

        conv1 = keras.layers.Conv1D(filters=128, kernel_size=8, padding='same')(input_layer)
        conv1 = keras.layers.BatchNormalization()(conv1)
        conv1 = keras.layers.Activation(activation='relu')(conv1)

        conv2 = keras.layers.Conv1D(filters=256, kernel_size=5, padding='same')(conv1)
        conv2 = keras.layers.BatchNormalization()(conv2)
        conv2 = keras.layers.Activation('relu')(conv2)

        conv3 = keras.layers.Conv1D(128, kernel_size=3,padding='same')(conv2)
        conv3 = keras.layers.BatchNormalization()(conv3)
        conv3 = keras.layers.Activation('relu')(conv3)

        gap_layer = keras.layers.GlobalAveragePooling1D()(conv3)

        output_layer = keras.layers.Dense(nb_classes, activation='softmax')(gap_layer)

        model = keras.models.Model(inputs=input_layer, outputs=output_layer)
        model = self.model_compile_and_callback(model)
        
        return model

    def model_compile_and_callback(self, model):
        model.compile(loss='categorical_crossentropy', optimizer = keras.optimizers.Adam(), 
            metrics=['accuracy'])

        reduce_lr = keras.callbacks.ReduceLROnPlateau(monitor='loss', factor=0.5, patience=50, 
            min_lr=0.0001)

        file_path = self.output_directory+'best_model.hdf5'

        model_checkpoint = keras.callbacks.ModelCheckpoint(filepath=file_path, monitor='loss', 
            save_best_only=True)

        self.callbacks = [reduce_lr, model_checkpoint]
        return model

    def freeze_and_change_last_layer(self, nb_classes, trainable_layers=None):
        num_layers = len(self.model.layers)
        print("*"*30, "old_model summary:", self.model.summary(), "*"*30)

        base_output = self.model.layers[num_layers-2].output # layer number obtained from model summary above
        new_output = tf.keras.layers.Dense(activation='softmax', units=nb_classes)(base_output)
        new_model = tf.keras.models.Model(inputs=self.model.inputs, outputs=new_output)
        
        # self.model = deepcopy(new_model)
        self.model = new_model
        print("*"*30, "new_model summary:", self.model.summary(), "*"*30)
        trainable_layers = ast.literal_eval(trainable_layers)
        for i, layer in enumerate(self.model.layers):
            if trainable_layers and i in trainable_layers:
                layer.trainable = True
            else:
                layer.trainable = False
            print(f'i:{i}, layer.name:{layer.name}, layer.trainable:{layer.trainable}')

    def fit(self, x_train, y_train, x_val, y_val, x_test, y_test, y_true, do_pred_only=False, nb_epochs=2000, batch_size=16, train_method='normal', trainable_layers=None, nb_classes=None):
        print("train_method:", train_method)
        nb_epochs = int(nb_epochs)
        batch_size = int(batch_size)
        if not tf.test.is_gpu_available:
            print('error')
            exit()
        if do_pred_only:
            results = self.model.evaluate(x_test, y_test, batch_size=128)
            print("results:", results)
            y_pred = self.model.predict(x_test)
            print("y_pred:", y_pred)
            # convert the predicted from binary to integer 
            y_pred = np.argmax(y_pred , axis=1)
        else:
            # x_val and y_val are only used to monitor the test loss and NOT for training  

            mini_batch_size = int(min(x_train.shape[0] / 10, batch_size))

            start_time = time.time() 
            if 'finetune' in train_method:
                self.freeze_and_change_last_layer(nb_classes, trainable_layers=trainable_layers)
                self.model = self.model_compile_and_callback(self.model)

            if x_val is not None and y_val is not None:
                hist = self.model.fit(x_train, y_train, batch_size=mini_batch_size, epochs=nb_epochs,
                    verbose=self.verbose, validation_data=(x_val, y_val), callbacks=self.callbacks)
            else:
                hist = self.model.fit(x_train, y_train, batch_size=mini_batch_size, epochs=nb_epochs,
                    verbose=self.verbose, callbacks=self.callbacks)
            
            duration = time.time() - start_time

            if 'normal' not in train_method:
                last_model_file_path = self.output_directory + f'{train_method}_last_model.hdf5'
                best_model_file_path = self.output_directory + f'{train_method}_best_model.hdf5'
                os.rename(self.output_directory + 'best_model.hdf5', best_model_file_path)
            else:
                last_model_file_path = self.output_directory + 'last_model.hdf5'
                best_model_file_path = self.output_directory + 'best_model.hdf5'

            self.model.save(last_model_file_path)
            model = keras.models.load_model(best_model_file_path)

            # y_pred = model.predict(x_val)
            y_pred = model.predict(x_test)

            # convert the predicted from binary to integer 
            y_pred = np.argmax(y_pred, axis=1)

            df_metrics = save_logs(self.output_directory, hist, y_pred, y_true, duration, train_method=train_method)

            keras.backend.clear_session()

            return df_metrics

    def predict(self, x_test, y_true,x_train,y_train,y_test,return_df_metrics = True):
        model_path = self.output_directory + 'best_model.hdf5'
        model = keras.models.load_model(model_path)
        y_pred = model.predict(x_test)
        if return_df_metrics:
            y_pred = np.argmax(y_pred, axis=1)
            df_metrics = calculate_metrics(y_true, y_pred, 0.0)
            return df_metrics
        else:
            return y_pred