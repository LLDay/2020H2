#include "client/client.h"
#include "ui_client.h"

#include "client/message_widget.h"

#include "io_operations.h"
#include "utils.h"

#include <QDateTime>
#include <QRegularExpression>
#include <QTimer>

#include <unistd.h>

Client::Client(
    QStringView name,
    const EndpointSetup & setup,
    QWidget * parent) noexcept
    : QMainWindow{parent},
      mSendClicked{false}, mName{name.toString()}, mSetup{setup.connection},
      mListener{setup.eventBufferSize, setup.timeout}, ui{new Ui::Client} {
    ui->setupUi(this);

    mBuilder.setOnFullReadCallback(
        [this](int s, Message m) { this->onMessageReceived(s, m); });

    QObject::connect(
        ui->sendButton, &QPushButton::clicked, this, &Client::onSendClicked);

    QObject::connect(
        &mListener, &EventListenerAdapter::incomingMessage, this,
        &Client::onIncomingMessage);

    QObject::connect(
        &mListener, &EventListenerAdapter::connectionLost, this,
        &Client::onConnectionLost);

    ui->messageTextEdit->setFocus();
    connectToServer();
}

Client::~Client() noexcept {
    delete ui;
    ::close(mSocket);
}

void Client::onIncomingMessage() noexcept {
    IoReadTask read{
        mSocket, &mBuilder, [this](int s) { this->mListener.oneshot(s); }};
    read.run();
}

void Client::onConnectionLost() noexcept {
    ::close(mSocket);
    logInfo("Disconnected from server");
    connectToServer();
}

void Client::onSendClicked() noexcept {
    static QRegularExpression middle{"[\\n]{2,}"};
    static QRegularExpression edge{"^\\n+|\\n+$"};

    auto text = ui->messageTextEdit->toPlainText().trimmed();

    if (text.isEmpty())
        return;

    text.replace(edge, "");
    text.replace(middle, "\n\n");

    Message message;
    message.author = mName.toUtf8().toStdString();
    message.text = text.toUtf8().toStdString();

    IoWriteTask writeTask{mSocket, message};
    writeTask.run();
    mSendClicked.store(true);
}

void Client::connectToServer() noexcept {
    auto connectionResult = connectedSocket(mSetup);
    if (connectionResult.socket >= 0)
        mSocket = connectionResult.socket;

    if (connectionResult.error == NET_ERROR::TEMPORARY) {
        ui->statusLabel->setText("No server connection");
        ui->statusLabel->show();
        QTimer::singleShot(RECONNECT_TIME, this, &Client::connectToServer);
        return;
    }

    if (connectionResult.error == NET_ERROR::CRITICAL) {
        close();
        ui->statusLabel->setText("Wrong ip address or port");
        ui->statusLabel->show();
        return;
    }

    makeNonBlocking(mSocket);
    ui->statusLabel->hide();
    mListener.add(mSocket);
}
void Client::onMessageReceived(int, Message message) noexcept {
    auto widget = new MessageWidget{message, ui->messagesListWidget};
    auto item = new QListWidgetItem{ui->messagesListWidget};
    item->setSizeHint(widget->sizeHint());
    ui->messagesListWidget->addItem(item);
    ui->messagesListWidget->setItemWidget(item, widget);
    ui->messagesListWidget->scrollToBottom();
    if (mSendClicked.exchange(false))
        ui->messageTextEdit->clear();
}
